"""Showing 27,000 markers is not showing the data; it is hiding it in noise.

A Jakarta-wide viewport holds 27,114 POIs across all thirty categories. Rendering
that many DOM markers is unusable, and silently dropping most of them is worse:
the map looks complete and is not.

So the layer aggregates instead of truncating. Below a threshold every point is
returned individually; above it, points are grouped on a grid and each group
reports its own count, so the total on screen still adds up to the total in the
viewport. Nothing is removed, and the response says which mode produced it.
"""
import math

import pytest

from api.services.poi_clustering import (
    CLUSTER_TARGET,
    cluster_cell_size,
    should_cluster,
)


def test_a_small_viewport_returns_individual_points():
    # A few hundred markers is readable and worth showing exactly.
    assert should_cluster(400, limit=2000) is False


def test_a_city_wide_viewport_clusters():
    # 27,114 is the measured count for Jakarta across all thirty categories.
    assert should_cluster(27114, limit=2000) is True


def test_the_threshold_is_the_row_limit_not_an_arbitrary_number():
    # Clustering exists because the limit would otherwise cut the layer. Tying
    # the decision to the same number keeps the two from drifting apart.
    assert should_cluster(2000, limit=2000) is False
    assert should_cluster(2001, limit=2000) is True


def test_cluster_cells_scale_with_the_viewport():
    # A fixed grid size would give one enormous blob when zoomed out and one
    # cluster per point when zoomed in. It has to follow the span on screen.
    wide = cluster_cell_size(west=106.25, east=107.25)
    narrow = cluster_cell_size(west=106.62, east=106.98)
    assert wide > narrow
    assert wide / narrow == pytest.approx((107.25 - 106.25) / (106.98 - 106.62))


def test_cluster_cells_divide_the_viewport_into_a_usable_number():
    # Roughly CLUSTER_TARGET cells across, so a zoomed-out map shows a legible
    # scatter of counts rather than either one dot or a thousand.
    span = 107.25 - 106.25
    assert cluster_cell_size(west=106.25, east=107.25) == pytest.approx(span / CLUSTER_TARGET)


def test_a_degenerate_viewport_still_yields_a_positive_cell():
    # west == east cannot happen through the API (parse_bbox rejects it), but a
    # zero or negative cell size would make ST_SnapToGrid divide by zero deep
    # inside Postgres, which is a far worse error to debug than this one.
    assert cluster_cell_size(west=106.5, east=106.5) > 0
    assert math.isfinite(cluster_cell_size(west=106.5, east=106.5))
