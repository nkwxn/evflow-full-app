"""Spreading the shortlist out geographically.

The pins used to come from ST_ClusterKMeans inside the ranking SQL. Moving the
clustering into Python is what lets a pin and the cell under it carry the same
number: the heatmap colour and the pin score now come from one function call
rather than from two implementations that agree by inspection.
"""

import pytest

from api.services.site_clustering import spread


def _pt(cell_id, lat, lon, score, station_count=0):
    return {"cell_id": cell_id, "latitude": lat, "longitude": lon,
            "score": score, "station_count": station_count}


def _grid(n=40):
    return [_pt(f"C{i:03d}", -6.1 - 0.01 * (i % 8), 106.7 + 0.01 * (i // 8),
                0.5 + 0.01 * i) for i in range(n)]


def test_a_cluster_is_reported_at_its_best_member_not_its_centroid():
    """A centroid lands in a river; a cell is somewhere a survey can be sent."""
    pts = [_pt("A", -6.10, 106.80, 0.9), _pt("B", -6.11, 106.81, 0.4),
           _pt("C", -6.30, 106.95, 0.8), _pt("D", -6.31, 106.96, 0.3)]
    out = spread(pts, 2)
    assert {p["cell_id"] for p in out} == {"A", "C"}
    for p in out:
        assert (p["latitude"], p["longitude"]) in {(-6.10, 106.80), (-6.30, 106.95)}


def test_the_same_request_twice_puts_the_pins_in_the_same_places():
    """sklearn seeds k-means randomly by default; ST_ClusterKMeans did not.

    Without random_state the pins jitter between two identical requests, which
    reads to a planner as the recommendation changing its mind.
    """
    pts = _grid()
    first = [p["cell_id"] for p in spread(pts, 6)]
    for _ in range(4):
        assert [p["cell_id"] for p in spread(pts, 6)] == first


def test_reordering_the_input_does_not_move_the_pins():
    pts = _grid()
    assert ({p["cell_id"] for p in spread(pts, 5)}
            == {p["cell_id"] for p in spread(list(reversed(pts)), 5)})


def test_k_is_clamped_to_what_there_is_to_cluster():
    pts = [_pt("A", -6.1, 106.8, 0.9), _pt("B", -6.2, 106.9, 0.8)]
    assert len(spread(pts, 15)) == 2
    assert len(spread(pts, 0)) == 1
    assert spread([], 5) == []


def test_longitude_is_projected_before_clustering():
    """At -6.2 deg a degree of longitude is ~1.006x a degree of latitude...

    ...so the correction is small here and the test has to be built to see it.
    Two pairs, one separated in latitude and one in longitude by the same NUMBER
    of degrees; under an unprojected metric they are equidistant and the split is
    arbitrary, and near the equator the projection barely moves that. The check
    that matters is that the function divides on real ground distance: at a high
    latitude, where cos shrinks longitude hard, the longitude-separated pair must
    end up together.
    """
    far_north = [_pt("N1", 60.00, 10.00, 0.9), _pt("N2", 60.00, 10.40, 0.8),
                 _pt("S1", 61.00, 10.00, 0.7), _pt("S2", 61.02, 10.00, 0.6)]
    out = spread(far_north, 2)
    # 0.40 deg of longitude at 60 deg N is ~22 km; 1.0 deg of latitude is ~111 km.
    # The pair that must NOT be split is the longitude one.
    assert {p["cell_id"] for p in out} == {"N1", "S1"}


def test_a_cell_that_already_holds_a_station_is_never_proposed():
    """Whatever it scores. Recommending a site where one already stands is
    indefensible, so this is a filter rather than a penalty."""
    pts = [_pt("BUILT", -6.10, 106.80, 0.99, station_count=1),
           _pt("FREE", -6.11, 106.81, 0.40),
           _pt("FAR", -6.30, 106.95, 0.80)]
    out = spread(pts, 2)
    assert {p["cell_id"] for p in out} == {"FREE", "FAR"}


def test_every_cell_holding_a_station_leaves_nothing_to_propose():
    pts = [_pt("A", -6.1, 106.8, 0.9, station_count=2)]
    assert spread(pts, 3) == []


def test_pins_come_back_best_first():
    out = spread(_grid(), 5)
    assert [p["score"] for p in out] == sorted((p["score"] for p in out), reverse=True)


def test_each_pin_reports_how_many_cells_it_stands_for():
    out = spread(_grid(40), 4)
    assert sum(p["cluster_size"] for p in out) == 40
    assert all(p["cluster_size"] >= 1 for p in out)


def test_clusters_are_geographically_separated():
    """Two tight blobs 30 km apart must not share a pin."""
    west = [_pt(f"W{i}", -6.10 + 0.001 * i, 106.70 + 0.001 * i, 0.5 + 0.001 * i)
            for i in range(10)]
    east = [_pt(f"E{i}", -6.10 + 0.001 * i, 107.00 + 0.001 * i, 0.5 + 0.001 * i)
            for i in range(10)]
    out = spread(west + east, 2)
    sides = {p["cell_id"][0] for p in out}
    assert sides == {"W", "E"}


def test_missing_coordinates_are_refused_rather_than_clustered_at_null_island():
    with pytest.raises(ValueError, match="latitude"):
        spread([_pt("A", None, 106.8, 0.9)], 1)
