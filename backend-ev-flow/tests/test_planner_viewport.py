"""The map sends the viewport and the layer name, so both are untrusted input.

The layer name is the dangerous one. It decides which column the heatmap colours
by, and a column name cannot be a bound parameter, so it reaches SQL as text. It
is therefore resolved through a fixed table rather than interpolated, and these
tests are what stop that table from being bypassed.

The viewport is the expensive one. Every cell it covers becomes a polygon in the
response, so a request that asks for the whole world is a request for the whole
grid, and the bounds are checked before any of that is read.
"""
import math

import pytest

from api.services.planner_viewport import (
    METRIC_COLUMNS,
    Viewport,
    metric_column,
    parse_bbox,
)


def test_parses_a_well_formed_viewport():
    v = parse_bbox("106.62,-6.38,106.98,-6.06")
    assert v == Viewport(west=106.62, south=-6.38, east=106.98, north=-6.06)


def test_wrong_number_of_values_is_rejected():
    for raw in ("106.62,-6.38,106.98", "106.62,-6.38,106.98,-6.06,11", ""):
        with pytest.raises(ValueError, match="four"):
            parse_bbox(raw)


def test_non_numeric_values_are_rejected():
    with pytest.raises(ValueError, match="number"):
        parse_bbox("106.62,-6.38,106.98,north")


def test_nan_and_infinity_are_rejected():
    # float() accepts both, and both would sail through a range comparison
    # silently: NaN fails every comparison, so `west < east` would not catch it.
    for raw in ("nan,-6.38,106.98,-6.06", "106.62,-6.38,inf,-6.06"):
        with pytest.raises(ValueError, match="finite"):
            parse_bbox(raw)
    assert not math.isnan(parse_bbox("106.62,-6.38,106.98,-6.06").west)


def test_coordinates_outside_the_world_are_rejected():
    with pytest.raises(ValueError, match="longitude"):
        parse_bbox("-181,-6.38,106.98,-6.06")
    with pytest.raises(ValueError, match="latitude"):
        parse_bbox("106.62,-91,106.98,-6.06")


def test_an_inverted_or_empty_viewport_is_rejected():
    # west == east selects nothing but still scans; it is a client bug, not a
    # legitimate request for an empty map.
    with pytest.raises(ValueError, match="west"):
        parse_bbox("106.98,-6.38,106.62,-6.06")
    with pytest.raises(ValueError, match="south"):
        parse_bbox("106.62,-6.06,106.98,-6.38")
    with pytest.raises(ValueError, match="west"):
        parse_bbox("106.62,-6.38,106.62,-6.06")


def test_whitespace_around_values_is_tolerated():
    assert parse_bbox(" 106.62 , -6.38 , 106.98 , -6.06 ").west == 106.62


def test_known_layers_resolve_to_a_column():
    for name in METRIC_COLUMNS:
        assert metric_column(name) == METRIC_COLUMNS[name]


def test_an_unknown_layer_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="unknown"):
        metric_column("secret_column")


def test_a_layer_name_cannot_smuggle_sql():
    # The whole reason the lookup exists. If any of these resolved, the caller
    # would be choosing the SQL rather than choosing a layer.
    for attack in ("population; DROP TABLE planning_cells",
                   "population --", "1) OR (1=1", "population, pg_sleep(10)"):
        with pytest.raises(ValueError, match="unknown"):
            metric_column(attack)


def test_every_mapped_column_is_a_bare_identifier():
    # Nothing in the table may carry an expression, because that is how a
    # harmless looking entry turns into an injection point later.
    for name, column in METRIC_COLUMNS.items():
        assert column.replace("_", "").isalnum(), f"{name} maps to {column!r}"


# ------------------------------------------------------ the POI marker layer

def test_every_poi_category_is_a_bare_identifier():
    # Each name is also a planning_cells column suffix (poi_mall, poi_cafe, ...).
    from api.services.planner_viewport import POI_CATEGORIES
    for name in POI_CATEGORIES:
        assert name.replace("_", "").isalnum(), f"{name!r} is not a bare identifier"


def test_the_api_whitelist_matches_what_the_database_allows():
    # Two lists of the same categories, one in Python and one in a CHECK
    # constraint. Drift between them fails in opposite directions and both are
    # quiet: a category the API accepts but the DB rejects blows up on insert,
    # and one the DB allows but the API does not is data nobody can ever see.
    # Pinning them to each other is cheaper than remembering.
    import re
    from pathlib import Path
    from api.services.planner_viewport import POI_CATEGORIES

    src = (Path(__file__).parents[1]
           / "alembic/versions/0022_poi_dwell_categories.py").read_text()
    in_migration = set(re.findall(r'"([a-z_]+)"', src.split("ALL_CATEGORIES")[0]))
    in_migration -= {"revision", "down_revision", "branch_labels", "depends_on"}
    assert in_migration == set(POI_CATEGORIES), (
        f"only in migration: {sorted(in_migration - set(POI_CATEGORIES))}; "
        f"only in API: {sorted(set(POI_CATEGORIES) - in_migration)}")


def test_the_dwell_categories_that_motivated_the_expansion_are_present():
    # The seventeen we started with had school and place_of_worship as 54% of
    # every POI, and only restaurant and mall on the commercial side. These are
    # the ones added to fix that; losing one silently would undo the point.
    from api.services.planner_viewport import POI_CATEGORIES
    for name in ("cafe", "fast_food", "supermarket", "hotel",
                 "office_commercial", "railway_station", "marketplace"):
        assert name in POI_CATEGORIES


def test_a_typo_in_a_category_is_refused_rather_than_returning_nothing():
    # Silently returning an empty layer for "restaurants" would look exactly
    # like "there are no restaurants here", which is a different claim.
    from api.services.planner_viewport import parse_poi_categories
    with pytest.raises(ValueError, match="unknown"):
        parse_poi_categories("restaurants")
    with pytest.raises(ValueError, match="unknown"):
        parse_poi_categories("mall,nope")


def test_no_category_filter_means_every_category():
    from api.services.planner_viewport import POI_CATEGORIES, parse_poi_categories
    assert parse_poi_categories(None) == list(POI_CATEGORIES)
    assert parse_poi_categories("") == list(POI_CATEGORIES)


def test_categories_are_parsed_as_a_list_and_deduplicated():
    from api.services.planner_viewport import parse_poi_categories
    assert parse_poi_categories("mall") == ["mall"]
    assert parse_poi_categories(" mall , restaurant ") == ["mall", "restaurant"]
    assert parse_poi_categories("mall,mall") == ["mall"]


def test_a_category_cannot_smuggle_sql():
    from api.services.planner_viewport import parse_poi_categories
    for attack in ("mall'; DROP TABLE planning_pois --", "mall OR 1=1", "*"):
        with pytest.raises(ValueError, match="unknown"):
            parse_poi_categories(attack)
