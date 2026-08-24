"""Rank the demand blend among STATIONS, not among cells.

WHY 0023 DID NOT SPREAD ENOUGH

0023 mapped a cell's demand percentile linearly onto a factor: 0.40 + 1.20 *
blend, rescaled so the mean across stations is 1.0. Measured on staging after
applying it, across 1,192 stations split into quartiles by factor:

    Q1  0.362 - 0.962   0.48 sessions per station
    Q2  0.963 - 1.035   0.63
    Q3  1.035 - 1.082   0.63
    Q4  1.082 - 1.155   0.65

Q4 drew only 1.35x Q1, and Q2 through Q4 were indistinguishable: three quarters
of all stations landed inside a 0.963 to 1.155 band. The cause is the same
clustering that broke the first attempt at the mean. Percentiles are uniform
across CELLS, and stations sit overwhelmingly in the high-percentile ones, so a
linear map compresses almost every station against the ceiling.

A target where 75% of the population is indistinguishable is not much better for
training than the random one it replaced.

WHAT THIS CHANGES

The blend is ranked a second time, among stations. PERCENT_RANK over stations is
uniform on [0, 1] by construction, so the factor spans its full range with
stations spread evenly through it and no rescale needed to hit a mean of 1.0.

The demand assumption itself is untouched: same three features, same weights.
Only the mapping from "how does this place compare" to "how much busier" changes,
and it changes from comparing against all of Jabodetabek's land to comparing
against the places charging actually happens.

Revision ID: 0024_demand_factor_station_rank
Revises: 0023_station_demand_factor
"""
from alembic import op

revision = "0024_demand_factor_station_rank"
down_revision = "0023_station_demand_factor"
branch_labels = None
depends_on = None


_FUNCTION = """
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
    per_station AS (
        SELECT s.id AS station_id, c.cell_id, b.blend
          FROM stations s
          JOIN planning_cells c ON ST_Within(s.geom, c.geom)
          JOIN blended b        ON b.cell_id = c.cell_id
    ),
    -- The second ranking, and the whole point of this migration. Uniform on
    -- [0, 1] across stations by construction, so 0.40 + 1.20 * rank spans
    -- 0.40 to 1.60 with a mean of exactly 1.0 and stations spread evenly
    -- through it. No rescale is needed and none is applied.
    station_rank AS (
        SELECT station_id, cell_id,
               PERCENT_RANK() OVER (ORDER BY blend) AS r
          FROM per_station
    )
    SELECT station_id,
           round((0.40 + 1.20 * r)::numeric, 3),
           cell_id
      FROM station_rank;

    SELECT count(*) INTO n FROM station_demand_factor;
    RETURN n;
END;
$$
"""

_PREVIOUS = """
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
"""


def upgrade() -> None:
    op.execute(_FUNCTION)


def downgrade() -> None:
    op.execute(_PREVIOUS)
