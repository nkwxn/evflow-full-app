"""One cell, three endpoints, one suitability number.

THE REGRESSION THIS FILE EXISTS TO CATCH

Before this, the map painted one quantity and the panel beside it printed
another, both labelled "demand". The heatmap came from the descriptive model,
the pins came from a weighted SQL formula, and the feasibility card came from a
third expression -- so "Located in a Red Demand Zone" on the card could sit next
to a cell the map had painted green, and nothing failed.

Sharing a function is not enough to prevent that coming back: the three paths
fetch different columns, and a divergence shows up as a silently different
number rather than an error. So the assertion is equality across all three.
"""
import pytest
from fastapi.testclient import TestClient

from api import planner_repo
from api.main import app, require_planner
from api.services import resemblance_scale, siting_model, suitability, utilisation_model

pytest.importorskip("sklearn")

CELL = "JBDTBK_00042"


FEATS = ["population", "road_length_m", "connectors", "avg_kw"]


@pytest.fixture
def artifact(tmp_path):
    """y = population + 10*connectors, so a prediction can be checked by hand."""
    import joblib
    import numpy as np
    from sklearn.linear_model import LinearRegression

    rng = np.random.default_rng(0)
    X = rng.uniform(1, 100, size=(60, 4))
    joblib.dump({
        "model": LinearRegression().fit(X, X[:, 0] + 10.0 * X[:, 2]),
        "feature_names": FEATS, "target": "sessions_per_conn_day",
        "target_units": "simulated charging sessions per connector per day",
        "reference_spec": {"connectors": 2.0, "avg_kw": 22.0},
        "trained_at": "2026-08-24T09:00:00+00:00",
        "window_start": "2026-08-21T00:00:00+07:00",
        "window_end": "2026-08-24T00:00:00+07:00",
        "window_days": 3, "dose_response_q4_over_q1": 1.64, "n_samples": 881,
        "loco_r2": 0.2744, "random_split_r2": 0.23, "median_sessions_per_cell": 29.0,
        "counting_noise_pct": 18.6, "sklearn_version": "1.7.2",
        "label": "utilisation SCENARIO",
    }, tmp_path / "u.joblib")
    utilisation_model.reset_cache()
    yield str(tmp_path / "u.joblib")
    utilisation_model.reset_cache()


def _cell(i, pop, stations=0, stations_2km=0, nearest_m=9000.0):
    """A row wide enough for every read path: the model's features, the supply
    columns suitability needs, and the display columns a pin is reported with."""
    return {"cell_id": f"JBDTBK_{i:05d}", "kota": "Jakarta Pusat",
            "population": pop, "road_length_m": 10.0 + i,
            "station_count": stations, "connector_count": stations * 2,
            "stations_2km": stations_2km, "nearest_station_m": nearest_m,
            "latitude": -6.10 - 0.004 * i, "longitude": 106.75 + 0.004 * i,
            "poi_total": int(pop // 10), "road_nodes": 5 + i,
            "score": 0.5, "rank_overall": i, "cells_total": 60,
            "in_scored_set": True, "overlap_frac": 1.0}


@pytest.fixture
def cells():
    """A spread-out grid: varied demand, varied supply, a few already built."""
    out = [_cell(i, 50.0 + 25.0 * i,
                 stations_2km=i % 5,
                 nearest_m=None if i % 7 == 0 else 300.0 + 400.0 * (i % 6))
           for i in range(1, 41)]
    for i in (3, 11, 27):
        out[i]["station_count"] = 1
        out[i]["connector_count"] = 2
    return out


@pytest.fixture
def wired(monkeypatch, artifact, cells):
    """One fake grid behind every planner read path."""
    by_id = {c["cell_id"]: c for c in cells}

    monkeypatch.setattr(utilisation_model, "DEFAULT_MODEL_PATH", artifact)
    monkeypatch.setattr(planner_repo, "supply_fingerprint", lambda: "stations=3;connectors=9")
    monkeypatch.setattr(planner_repo, "features_for_scoring", lambda names, **kw: cells)
    monkeypatch.setattr(planner_repo, "features_for_unbuilt_cells", lambda names, **kw: cells)
    monkeypatch.setattr(planner_repo, "features_in_radius",
                        lambda *a, **k: (cells, len(cells)))
    monkeypatch.setattr(planner_repo, "candidate_cells",
                        lambda names, **kw: [c for c in cells if not c["station_count"]])
    monkeypatch.setattr(planner_repo, "get_cell", lambda cid: dict(by_id[cid]))
    monkeypatch.setattr(siting_model, "predict", lambda rows, path=None: [0.5] * len(rows))
    resemblance_scale.reset_cache()
    suitability.reset_cache()
    app.dependency_overrides[require_planner] = lambda: {"id": "u",
                                                         "account_type": "business_planner"}
    yield TestClient(app)
    app.dependency_overrides.pop(require_planner, None)
    resemblance_scale.reset_cache()
    suitability.reset_cache()


def test_the_map_the_pin_and_the_card_report_the_same_suitability(wired):
    area = wired.get("/api/v1/planner/predict.area"
                     "?lat=-6.17&lon=106.82&radius_km=25&limit=5000&top=5000").json()
    from_map = {p["cell_id"]: p["suitability"] for p in area["predictions"]}

    pins = wired.post("/api/v1/planner/candidates?basis=suitability&clusters=12",
                      json={"coverage": 0.25, "population": 0.25,
                            "activity": 0.25, "roads": 0.25}).json()
    assert pins["basis"] == "suitability", "the model was available; it should have been used"
    assert pins["candidates"], "a shortlist of nothing proves nothing"

    for pin in pins["candidates"]:
        cell = wired.get(f"/api/v1/planner/cells/{pin['cell_id']}").json()
        assert pin["score"] == pytest.approx(from_map[pin["cell_id"]], abs=5e-4)
        assert cell["suitability"] == pytest.approx(from_map[pin["cell_id"]], abs=5e-4)
        assert cell["suitability_band"] == pin["suitability_band"]


def test_a_pin_is_never_placed_where_a_station_already_stands(wired):
    pins = wired.post("/api/v1/planner/candidates?basis=suitability&clusters=20",
                      json={"coverage": 0.25, "population": 0.25,
                            "activity": 0.25, "roads": 0.25}).json()
    assert all(p["station_count"] == 0 for p in pins["candidates"])


def test_the_weighted_basis_is_what_you_get_unless_you_ask(wired, monkeypatch):
    monkeypatch.setattr(planner_repo, "candidate_sites",
                        lambda *a, **k: [{"cluster_id": 0, "cell_id": CELL, "kota": "Depok",
                                          "score": 0.77, "latitude": -6.4, "longitude": 106.8,
                                          "population": 1.0, "poi_total": 1,
                                          "station_count": 0, "nearest_station_m": 500.0,
                                          "stations_2km": 1, "cluster_size": 1}])
    body = wired.post("/api/v1/planner/candidates",
                      json={"coverage": 0.25, "population": 0.25,
                            "activity": 0.25, "roads": 0.25}).json()
    assert body["basis"] == "weighted"
    assert body["candidates"][0]["suitability_band"] is None


def test_asking_for_suitability_without_a_model_answers_and_says_which(wired, monkeypatch):
    """Not a 503. The caller wants suggestions; the weighted score is a real
    answer to that, and `basis` is how they find out which one they got."""
    monkeypatch.setattr(planner_repo, "candidate_sites",
                        lambda *a, **k: [{"cluster_id": 0, "cell_id": CELL, "kota": "Depok",
                                          "score": 0.77, "latitude": -6.4, "longitude": 106.8,
                                          "population": 1.0, "poi_total": 1,
                                          "station_count": 0, "nearest_station_m": 500.0,
                                          "stations_2km": 1, "cluster_size": 1}])
    monkeypatch.setattr(utilisation_model, "DEFAULT_MODEL_PATH", "/nonexistent/model.joblib")
    suitability.reset_cache()
    r = wired.post("/api/v1/planner/candidates?basis=suitability",
                   json={"coverage": 0.25, "population": 0.25,
                         "activity": 0.25, "roads": 0.25})
    assert r.status_code == 200
    assert r.json()["basis"] == "weighted"
