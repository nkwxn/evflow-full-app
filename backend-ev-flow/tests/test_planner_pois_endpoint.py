"""The POI marker layer has to stay honest about what it is not showing.

A marker layer is read as "here is what is here". When the row limit cuts it,
that reading becomes false, and the failure is silent: the map looks finished.
So the response carries the per-category totals it was cut from, and the cut
itself is round-robin so the surviving markers stay proportional instead of
being all parking and no malls.
"""
import pytest
from fastapi.testclient import TestClient

from api import planner_repo
from api.main import app, require_planner

BBOX = "106.62,-6.38,106.98,-6.06"


def _row(i, cat):
    return {"id": i, "osm_id": 1000 + i, "category": cat, "name": f"{cat}-{i}",
            "cell_id": "JBDTBK_00001", "lon": 106.8 + i / 1000, "lat": -6.2 - i / 1000}


@pytest.fixture
def client(monkeypatch):
    rows = [_row(1, "mall"), _row(2, "restaurant"), _row(3, "parking")]
    monkeypatch.setattr(planner_repo, "pois_geojson", lambda v, c, limit=2000: rows[:limit])
    monkeypatch.setattr(planner_repo, "pois_in_viewport",
                        lambda v, c: {"mall": 1, "restaurant": 1, "parking": 900})
    monkeypatch.setattr(planner_repo, "pois_clustered",
                        lambda v, c, cell, limit=2000: [
                            {"n": 900, "top_category": "parking", "lon": 106.8, "lat": -6.2},
                            {"n": 2, "top_category": "mall", "lon": 106.85, "lat": -6.25}])
    app.dependency_overrides[require_planner] = lambda: {"id": "u", "account_type": "business_planner"}
    yield TestClient(app)
    app.dependency_overrides.pop(require_planner, None)


def test_features_are_geojson_points_in_longitude_latitude_order(client):
    # Leaflet takes latitude first. Getting this backwards puts every marker in
    # the Indian Ocean, which is obvious on a map and invisible in a test that
    # only checks the status code.
    f = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}").json()["features"][0]
    assert f["geometry"]["type"] == "Point"
    lon, lat = f["geometry"]["coordinates"]
    assert 106 < lon < 108, "longitude first"
    assert -7 < lat < -5, "latitude second"


def test_properties_carry_the_cell_so_a_marker_can_be_traced_to_its_count(client):
    props = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}").json()["features"][0]["properties"]
    assert props["cell_id"] == "JBDTBK_00001"
    assert props["category"] == "mall"


def test_the_response_reports_what_it_was_cut_from(client):
    # 900 parking exist in the viewport; three rows came back. Without this the
    # layer would look complete.
    body = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}").json()
    assert body["pois_in_viewport"]["parking"] == 900
    assert body["pois_returned"] == 3


def test_a_crowded_viewport_clusters_rather_than_truncating(client):
    # The fixture's viewport holds 902 POIs. Asked for a limit of 2, the old
    # behaviour returned 2 markers and called itself truncated, which drew a map
    # that looked complete and was missing 900 places. Now it groups them, and
    # every POI is still represented inside a feature carrying its own count.
    body = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}&limit=2").json()
    assert body["mode"] == "clustered"
    assert all(f["properties"]["cluster"] is True for f in body["features"])
    assert all("count" in f["properties"] for f in body["features"])


def test_a_quiet_viewport_returns_individual_points(client):
    body = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}&limit=5000").json()
    assert body["mode"] == "points"
    assert body["truncated"] is False
    assert all(f["properties"]["cluster"] is False for f in body["features"])


def test_the_viewport_total_is_reported_in_both_modes(client):
    # This is the denominator that keeps either mode honest: whatever is drawn,
    # the client can always say how many POIs are really there.
    for limit in (2, 5000):
        body = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}&limit={limit}").json()
        assert sum(body["pois_in_viewport"].values()) == 902


def test_the_categories_covered_are_echoed_back(client):
    body = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}&categories=mall,restaurant").json()
    assert body["categories"] == ["mall", "restaurant"]
    # Omitting the filter must mean every category, not an empty layer. Pinned
    # to the whitelist rather than to a number, so growing the list does not
    # need this test edited -- which is how the number went stale last time.
    from api.services.planner_viewport import POI_CATEGORIES
    everything = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}").json()["categories"]
    assert everything == list(POI_CATEGORIES)


def test_a_mistyped_category_is_refused_not_silently_empty(client):
    r = client.get(f"/api/v1/planner/pois.geojson?bbox={BBOX}&categories=restaurants")
    assert r.status_code == 422
    assert "unknown POI category" in r.json()["detail"]


def test_a_malformed_viewport_is_refused(client):
    for bad in ("106.98,-6.38,106.62,-6.06", "106.62,-6.38,106.98", "nan,-6.38,106.98,-6.06"):
        assert client.get(f"/api/v1/planner/pois.geojson?bbox={bad}").status_code == 422


def test_the_layer_is_planner_only():
    # Removing the override entirely: an anonymous caller must not reach it.
    app.dependency_overrides.pop(require_planner, None)
    assert TestClient(app).get(f"/api/v1/planner/pois.geojson?bbox={BBOX}").status_code == 401
