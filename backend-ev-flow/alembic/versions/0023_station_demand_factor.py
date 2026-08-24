"""Per-station demand factor, so simulated occupancy varies by location.

WHAT THIS IS FOR

The live simulation (scripts/sql/charging_simulation.sql, by M Aidil Akbar) gives
EVERY free connector in Jabodetabek the same chance of starting a session in a
given 15-minute window. req_threshold depends on hour-of-day and weekday only:
there is no population, no POI, no geometry anywhere in the procedure.

Measured consequence: a station's occupancy is random sessions divided by its
connector count, and nothing else. Trained on 881 cells with leave-one-area-out
validation, 37 location features predict that occupancy at R2 = -0.063, worse
than guessing the mean. Connector count alone scores +0.437, and adding the
location features DROPS it to +0.412. They are noise.

That makes a prescriptive utilisation model impossible to train: the target
carries no information about place.

WHAT THIS CHANGES, AND WHAT IT DOES NOT

This table gives each station a multiplier on that threshold, derived from the
demand side of its cell. Sessions then concentrate where the assumptions say
demand is, and a model trained on the resulting occupancy recovers those
assumptions.

BE CLEAR ABOUT WHAT THAT IS. It is circular by construction: you get back what
you put in. It is NOT a forecast and must never be labelled as one. It is a
scenario tool, and a legitimate one: "if demand follows population, activity and
roads with these weights, here is where utilisation lands". The weights below are
the assumption, and they are the knob a planner should argue about.

WHY COVERAGE IS EXCLUDED

The product's weighted score uses coverage (distance to the nearest existing
station) at 0.35. That belongs in a siting score and not here: utilisation is
about how much demand reaches a charger, and feeding "far from other stations"
into the demand assumption would make an isolated rural charger look busy purely
because it is isolated.

WHY THE DEFAULT IS 1.0

Deploying the procedure change with this table empty leaves behaviour bit-for-bit
identical to today. That is deliberate: the procedure edit and the behaviour
change can be reviewed and rolled out separately, and a rollback is a DELETE
rather than a code revert.

Revision ID: 0023_station_demand_factor
Revises: 0022_poi_dwell_categories
"""
from alembic import op

revision = "0023_station_demand_factor"
down_revision = "0022_poi_dwell_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS station_demand_factor (
            station_id  TEXT PRIMARY KEY REFERENCES stations(id) ON DELETE CASCADE,
            factor      NUMERIC(5,3) NOT NULL CHECK (factor > 0 AND factor <= 5),
            cell_id     TEXT,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Percentile ranks, not raw values. Population runs 0 to 10,656 and
    # road_nodes 0 to a few hundred; multiplying raw numbers together would let
    # whichever has the larger units decide the answer on its own.
    #
    # The three weights renormalise the product's demand-side criteria
    # (population 0.35, activity 0.20, roads 0.10) to sum to 1. Coverage is
    # deliberately absent; see the module docstring.
    #
    # The raw factor is then RESCALED so its mean across stations is exactly 1.0.
    #
    # That step is not cosmetic. Percentile ranks are uniform across CELLS, but
    # stations are not spread uniformly across cells: they cluster in the
    # high-population, high-POI ones. Measured on staging, the unscaled factor
    # averaged 1.378 over 1,192 stations, so deploying it would have raised total
    # simulated session volume by 38% and changed the whole load profile rather
    # than only its distribution. Rescaling keeps the total where it is, which is
    # the only way a before/after comparison means anything.
    #
    # Rescaling preserves ratios, so the busiest location still draws about 3.2x
    # the quietest.
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_station_demand_factor()
        RETURNS INTEGER LANGUAGE plpgsql AS $$
        DECLARE
            n INTEGER;
        BEGIN
            DELETE FROM station_demand_factor;

            INSERT INTO station_demand_factor (station_id, factor, cell_id)
            WITH ranked AS (
                SELECT cell_id,
                       PERCENT_RANK() OVER (ORDER BY population)  AS r_population,
                       PERCENT_RANK() OVER (ORDER BY poi_total)   AS r_activity,
                       PERCENT_RANK() OVER (ORDER BY road_nodes)  AS r_roads
                  FROM planning_cells
                 WHERE overlap_frac >= 0.5 AND kota <> 'Kepulauan Seribu'
            ),
            blended AS (
                SELECT cell_id,
                       r_population * 0.53 + r_activity * 0.30 + r_roads * 0.17 AS blend
                  FROM ranked
            ),
            raw AS (
                SELECT s.id AS station_id,
                       0.40 + 1.20 * b.blend AS raw_factor,
                       c.cell_id
                  FROM stations s
                  JOIN planning_cells c ON ST_Within(s.geom, c.geom)
                  JOIN blended b        ON b.cell_id = c.cell_id
            ),
            scale AS (SELECT avg(raw_factor) AS mean_raw FROM raw)
            SELECT raw.station_id,
                   round(GREATEST(0.05, raw.raw_factor / scale.mean_raw)::numeric, 3),
                   raw.cell_id
              FROM raw, scale;

            SELECT count(*) INTO n FROM station_demand_factor;
            RETURN n;
        END;
        $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS refresh_station_demand_factor()")
    op.execute("DROP TABLE IF EXISTS station_demand_factor")
