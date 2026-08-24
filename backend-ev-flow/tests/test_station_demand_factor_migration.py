"""The demand factor that makes simulated occupancy depend on location.

Source-level contract, matching test_planner_saved_sites_migration: these assert
the decisions that are easy to undo by accident, not that Postgres works.

Why the migration exists at all: the simulation gives every free connector in
Jabodetabek the same chance of starting a session, so a station's occupancy is
random sessions divided by its connector count. Measured on 881 cells with
leave-one-area-out validation, 37 location features predict that at R2 = -0.063,
worse than guessing the mean, while connector count alone scores +0.437. Nothing
prescriptive can be trained on a target with no information about place.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MIGRATION = (ROOT / "alembic/versions/0023_station_demand_factor.py").read_text()
RANKED = (ROOT / "alembic/versions/0024_demand_factor_station_rank.py").read_text()
PROCEDURE = (ROOT / "scripts/sql/charging_simulation.sql").read_text()


def test_it_follows_the_poi_migration():
    assert 'down_revision = "0022_poi_dwell_categories"' in MIGRATION


def test_the_factor_is_rescaled_to_average_one_across_stations():
    # Not cosmetic. Percentile ranks are uniform across CELLS, but stations
    # cluster in the high-population, high-POI ones: measured on staging the
    # unscaled factor averaged 1.378 over 1,192 stations, so shipping it would
    # have raised total simulated volume by 38% and changed the load profile
    # rather than only its distribution.
    assert "scale AS (SELECT avg(raw_factor) AS mean_raw FROM raw)" in MIGRATION
    assert "raw.raw_factor / scale.mean_raw" in MIGRATION


def test_coverage_is_not_part_of_the_demand_assumption():
    # The siting score weights coverage at 0.35, and it has no place here:
    # utilisation is about demand reaching a charger, and "far from other
    # stations" would make an isolated rural charger look busy for being
    # isolated.
    demand_block = MIGRATION[MIGRATION.index("WITH ranked AS"):MIGRATION.index("scale AS")]
    assert "nearest_station_m" not in demand_block
    assert "stations_2km" not in demand_block


def test_the_factor_can_never_reach_zero():
    # A factor of zero would silence a station permanently, which is a different
    # claim from "quieter than average".
    assert "GREATEST(0.05" in MIGRATION
    assert "CHECK (factor > 0 AND factor <= 5)" in MIGRATION


def test_it_drops_cleanly():
    assert "DROP FUNCTION IF EXISTS refresh_station_demand_factor()" in MIGRATION
    assert "DROP TABLE IF EXISTS station_demand_factor" in MIGRATION


# --- the procedure that reads it ------------------------------------------------

def test_an_empty_table_leaves_the_simulation_behaving_exactly_as_before():
    # THE property that lets the code change and the behaviour change roll out
    # separately, and makes a rollback a DELETE rather than a revert.
    assert "COALESCE(f.factor, 1.0) AS demand_factor" in PROCEDURE
    assert "LEFT JOIN station_demand_factor f ON f.station_id = c.station_id" in PROCEDURE


def test_the_factor_is_joined_not_looked_up_per_connector():
    # The loop walks about 6,700 free connectors every 15 minutes.
    assert "SELECT (SELECT factor" not in PROCEDURE
    assert PROCEDURE.count("station_demand_factor") <= 4


def test_the_threshold_stays_inside_the_range_it_is_compared_against():
    # random_int is floor(random() * 100), so a threshold above 100 would make a
    # station fire every window and below 0 would silence it.
    assert "LEAST(100, GREATEST(0, round(req_threshold * conn.demand_factor)::INT))" in PROCEDURE


@pytest.mark.parametrize("phrase", ["SCENARIO, not a forecast", "recovers that assumption"])
def test_the_procedure_says_plainly_that_this_is_an_assumption(phrase):
    # A model trained on this output predicts the assumption, not reality.
    # Whoever reads this file next needs to know that before quoting a number
    # from it.
    assert phrase in PROCEDURE


# --- 0024, the second ranking ---------------------------------------------------

def test_the_blend_is_ranked_among_stations_not_only_among_cells():
    # 0023 alone left three quarters of stations inside a 0.963 to 1.155 band, so
    # Q2 through Q4 were indistinguishable and Q4 drew only 1.35x Q1. Percentiles
    # are uniform across CELLS and stations sit overwhelmingly in the
    # high-percentile ones, so a linear map compresses them against the ceiling.
    assert 'down_revision = "0023_station_demand_factor"' in RANKED
    assert "PERCENT_RANK() OVER (ORDER BY blend) AS r" in RANKED
    assert "0.40 + 1.20 * r" in RANKED


def test_the_second_ranking_needs_no_rescale():
    # PERCENT_RANK over stations is uniform on [0, 1] by construction, so the
    # mean is exactly 1.0 without the correction 0023 needed. Measured after
    # applying: mean 1.000, range 0.400 to 1.600, quartiles evenly spread.
    upgrade = RANKED[RANKED.index("_FUNCTION = "):RANKED.index("_PREVIOUS = ")]
    assert "mean_raw" not in upgrade


def test_the_demand_assumption_itself_is_unchanged():
    # Only the mapping from "how does this place compare" to "how much busier"
    # moved. Same three features, same weights, so the scenario being modelled is
    # the same one and the before/after is about spread alone.
    assert "r_population * 0.53 + r_activity * 0.30 + r_roads * 0.17" in RANKED


def test_it_can_be_rolled_back_to_the_previous_mapping():
    # The downgrade restores 0023's function rather than dropping it, so a
    # rollback leaves a working refresh rather than a missing one.
    previous = RANKED[RANKED.index("_PREVIOUS = "):]
    assert "mean_raw" in previous
    assert "CREATE OR REPLACE FUNCTION refresh_station_demand_factor()" in previous
