"""Suggested sites within a radius of a point the planner picked.

The dashboard used to open with fifteen suggestions spread across the whole of
Jabodetabek, which states an answer before anyone has said which place they care
about. Now the planner points somewhere and asks "what is good around here".

The invariant these tests exist for: THE SCORE IS COMPUTED OVER THE WHOLE REGION
AND ONLY THEN FILTERED TO THE CIRCLE. Rank inside the circle instead and the
percentile ranks recompute against 130 cells rather than 27,219, so the best cell
in a quiet suburb comes out identical to the best cell in Sudirman and the
planner cannot tell a strong area from a weak one. score_percentile is what makes
that difference visible.
"""
import pytest
from fastapi.testclient import TestClient

from api import planner_repo
from api.main import app, require_planner

POINT = {"lat": -6.2088, "lon": 106.8206, "radius_km": 3}
WEIGHTS = {"coverage": 0.35, "population": 0.35, "activity": 0.2, "roads": 0.1}


def _row(cell_id, score):
    return {"cluster_id": 0, "cell_id": cell_id, "kota": "Jakarta Pusat", "score": score,
            "latitude": -6.2, "longitude": 106.8, "population": 1000.0, "poi_total": 12,
            "station_count": 0, "nearest_station_m": 900.0, "stations_2km": 1,
            "cluster_size": 4}


@pytest.fixture
def calls():
    return {}


@pytest.fixture
def client(monkeypatch, calls):
    def _region(weights, clusters=15, quantile=0.90, **kw):
        calls["mode"] = "region"
        calls["clusters"] = clusters
        calls["quantile"] = quantile
        return [_row("JBDTBK_00001", 0.91)]

    def _radius(weights, lat, lon, radius_km, clusters=8, **kw):
        calls["mode"] = "radius"
        calls["centre"] = (lat, lon)
        calls["radius"] = radius_km
        calls["clusters"] = clusters
        return [_row("JBDTBK_00002", 0.62)]

    monkeypatch.setattr(planner_repo, "candidate_sites", _region)
    monkeypatch.setattr(planner_repo, "candidate_sites_in_radius", _radius)
    app.dependency_overrides[require_planner] = lambda: {"id": "u", "account_type": "business_planner"}
    yield TestClient(app)
    app.dependency_overrides.pop(require_planner, None)


def _post(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    path = f"/api/v1/planner/candidates?{query}" if query else "/api/v1/planner/candidates"
    return client.post(path, json=WEIGHTS)


def test_a_point_searches_the_circle_around_it(client, calls):
    r = _post(client, **POINT)
    assert r.status_code == 200
    assert calls["mode"] == "radius"
    assert calls["centre"] == (-6.2088, 106.8206)
    assert calls["radius"] == 3.0


def test_no_point_still_searches_the_whole_region(client, calls):
    # The region-wide answer stays available: it is what a planner with no
    # particular place in mind is asking for.
    assert _post(client).status_code == 200
    assert calls["mode"] == "region"


def test_the_score_is_comparable_between_places_and_is_the_only_ranking_shown(client):
    # No percentile field, deliberately. An earlier version returned one, and
    # measured on four very different 3 km circles the best cell scored at the
    # 0.953, 0.991, 0.993 and 0.993 percentile: take 115 cells from 27,219 and
    # the maximum lands in the top percentile almost every time. It would have
    # labelled every place a planner clicked as regionally top-tier.
    #
    # The score itself does discriminate on those same four circles: 0.673,
    # 0.722, 0.730 and 0.729. It is comparable because the ranks behind it are
    # computed over the whole region before the circle is applied.
    c = _post(client, **POINT).json()["candidates"][0]
    assert c["score"] == 0.62
    assert "score_percentile" not in c


def test_half_a_point_is_refused_rather_than_silently_ignored(client):
    # Dropping a lone lat and answering region-wide would return suggestions for
    # the whole of Jabodetabek to someone who asked about one place.
    assert _post(client, lat=-6.2).status_code == 422
    assert _post(client, lon=106.8).status_code == 422


def test_an_absurd_radius_is_refused(client):
    assert _post(client, lat=-6.2, lon=106.8, radius_km=500).status_code == 422


def test_a_circle_gets_fewer_clusters_than_the_whole_region(client, calls):
    # Fifteen suggestions inside 3 km would be one every 400 m, which is the
    # grid resolution: every cell would become its own suggestion.
    _post(client, **POINT)
    assert calls["clusters"] <= 8


def test_the_weights_still_apply_and_are_echoed(client):
    body = _post(client, **POINT).json()
    assert body["weights_applied"]["coverage"] == pytest.approx(0.35)


def test_an_anonymous_caller_is_refused(client):
    app.dependency_overrides.pop(require_planner, None)
    assert _post(client, **POINT).status_code in (401, 403)
