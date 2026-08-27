"""The prescriptive model: what it predicts, and what must never reach it.

WHY THIS MODEL EXISTS ALONGSIDE THE DESCRIPTIVE ONE

The siting model scores how much a cell resembles the ones that already hold a
station. Measured on the full grid its 500 highest cells are 100% cells that
already have one, so it cannot rank a place nobody has built on. This one
predicts sessions per connector per day and can, which is why it now decides the
ORDER of the area response while resemblance stays alongside as context.

THE INVARIANT THAT CARRIES MOST OF THESE TESTS

`connectors` and `avg_kw` are not properties of a place. They are what a planner
chooses to build there, they carry 57% of the model's importance, and
planning_cells has neither column. So they are injected from one reference spec
and never read from a row. If two callers could each supply their own, they would
compare cells at different specs and be comparing chargers rather than places --
silently, because both answers are well-formed numbers.
"""
import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LinearRegression

from api import planner_repo
from api.main import app, require_planner
from api.services import resemblance_scale, siting_model, utilisation_model

FEATS = ["population", "road_length_m", "connectors", "avg_kw"]
SPEC = {"connectors": 2.0, "avg_kw": 22.0}


@pytest.fixture
def artifact(tmp_path):
    """A model whose output is checkable by hand: y = pop + 10*connectors.

    A fitted forest would make every assertion a magic number nobody can verify.
    A linear fit on exactly-linear data recovers its coefficients, so the
    expected prediction can be written out in the test instead of copied from a
    previous run.
    """
    rng = np.random.default_rng(0)
    X = rng.uniform(1, 100, size=(60, 4))
    y = X[:, 0] + 10.0 * X[:, 2]
    path = tmp_path / "utilisation_model.joblib"
    joblib.dump({
        "model": LinearRegression().fit(X, y),
        "feature_names": FEATS,
        "target": "sessions_per_conn_day",
        "target_units": "simulated charging sessions per connector per day",
        "reference_spec": dict(SPEC),
        "trained_at": "2026-08-24T09:00:00+00:00",
        "window_start": "2026-08-21T00:00:00+07:00",
        "window_end": "2026-08-24T00:00:00+07:00",
        "window_days": 3,
        "dose_response_q4_over_q1": 1.64,
        "n_samples": 881,
        "loco_r2": 0.2744,
        "random_split_r2": 0.2300,
        "median_sessions_per_cell": 29.0,
        "counting_noise_pct": 18.6,
        "sklearn_version": "1.7.2",
        "label": "utilisation SCENARIO (recovers the demand assumption, not a forecast)",
    }, path)
    utilisation_model.reset_cache()
    yield str(path)
    utilisation_model.reset_cache()


# --- the hardware split --------------------------------------------------------

def test_location_features_exclude_the_hardware_the_table_does_not_have(artifact):
    i = utilisation_model.info(artifact)
    assert i.location_features == ["population", "road_length_m"]
    assert i.reference_spec == SPEC
    # Asking planning_cells for these is what trips the repo's staleness check
    # and turns an added capability into a 503 on the whole endpoint.
    assert "connectors" not in i.location_features
    assert "avg_kw" not in i.location_features


def test_hardware_is_injected_from_the_spec_not_read_from_the_row(artifact):
    # y = population + 10*connectors, and connectors is pinned at 2 by the spec.
    got = utilisation_model.predict([{"population": 500.0, "road_length_m": 9.0}], path=artifact)
    assert got[0] == pytest.approx(500.0 + 20.0, rel=1e-6)


def test_a_different_spec_moves_every_cell_together(artifact):
    rows = [{"population": p, "road_length_m": 1.0} for p in (100.0, 200.0)]
    base = utilisation_model.predict(rows, path=artifact)
    richer = utilisation_model.predict(rows, spec={"connectors": 6.0}, path=artifact)
    assert [b + 40.0 for b in base] == pytest.approx(richer, rel=1e-6)


def test_a_row_supplying_hardware_is_refused(artifact):
    with pytest.raises(ValueError, match="pass them in spec="):
        utilisation_model.predict(
            [{"population": 1.0, "road_length_m": 1.0, "connectors": 8.0}], path=artifact)


def test_a_spec_key_the_model_has_no_feature_for_is_refused(artifact):
    with pytest.raises(ValueError, match="no feature for"):
        utilisation_model.predict([{"population": 1.0, "road_length_m": 1.0}],
                                  spec={"solar_panels": 3.0}, path=artifact)


def test_a_missing_feature_is_an_error_rather_than_a_zero(artifact):
    # Zero population is a meaningful value, so defaulting the gap would answer a
    # question about a place that does not exist.
    with pytest.raises(ValueError, match="missing 1 feature"):
        utilisation_model.predict([{"population": 1.0}], path=artifact)


def test_a_missing_artifact_names_the_script_that_builds_it(tmp_path):
    utilisation_model.reset_cache()
    with pytest.raises(FileNotFoundError, match="train_utilisation_model.py"):
        utilisation_model.info(str(tmp_path / "absent.joblib"))


# --- the endpoint --------------------------------------------------------------

class _SitingInfo:
    trained_at = "2026-08-22T00:00:00+00:00"
    n_samples, n_positive = 27219, 885
    loco_auc, random_split_auc = 0.814, 0.927
    label, sklearn_version = "station presence", "1.7.2"
    feature_names = ["population", "road_length_m"]


def _cell(i, pop, stations=0, stations_2km=0, nearest_m=9000.0):
    return {"cell_id": f"JBDTBK_{i:05d}", "kota": "Jakarta Pusat", "station_count": stations,
            "population": pop, "road_length_m": 10.0,
            "stations_2km": stations_2km, "nearest_station_m": nearest_m}


@pytest.fixture
def client(monkeypatch, artifact):
    # Resemblance and utilisation are deliberately OPPOSED here: the cell that
    # looks most like an existing station is the emptiest, and the busiest
    # predicted cell looks least like one. A response ordered by the wrong model
    # cannot pass by accident.
    cells = [_cell(1, 10.0, stations=2), _cell(2, 20.0), _cell(3, 900.0), _cell(4, 400.0)]
    # Keyed by population, because cell_id never reaches the model: main.py
    # filters each row down to the model's own feature list first, which is the
    # behaviour test_only_the_models_own_features_reach_it pins next door.
    resemblance = {10.0: 0.90, 20.0: 0.80, 900.0: 0.10, 400.0: 0.20, 5.0: 0.95}

    def _radius(lat, lon, radius_km, names, limit=30000, **kw):
        return cells[:limit], len(cells)

    monkeypatch.setattr(planner_repo, "features_in_radius", _radius)
    monkeypatch.setattr(planner_repo, "features_in_area",
                        lambda v, names, limit=30000, **kw: (cells[:limit], len(cells)))
    monkeypatch.setattr(planner_repo, "features_for_unbuilt_cells",
                        lambda names, **kw: [_cell(9, 5.0)])
    monkeypatch.setattr(planner_repo, "features_for_cells",
                        lambda ids, names: [c for c in cells if c["cell_id"] in ids])
    # The suitability scale is regional, so it reads its own population rather
    # than the viewport's. Stubbed to the same cells here: the point of these
    # tests is the ordering and the fields, not the scale's own arithmetic,
    # which test_suitability covers without a database.
    monkeypatch.setattr(planner_repo, "features_for_scoring", lambda names, **kw: cells)
    monkeypatch.setattr(planner_repo, "supply_fingerprint", lambda: "test/fixture")
    monkeypatch.setattr(siting_model, "info", lambda path=None: _SitingInfo())
    monkeypatch.setattr(
        siting_model, "predict",
        lambda rows, path=None: [resemblance.get(float(r["population"]), 0.5) for r in rows])
    monkeypatch.setattr(utilisation_model, "DEFAULT_MODEL_PATH", artifact)
    resemblance_scale.reset_cache()
    app.dependency_overrides[require_planner] = lambda: {"id": "u",
                                                         "account_type": "business_planner"}
    yield TestClient(app)
    app.dependency_overrides.pop(require_planner, None)
    resemblance_scale.reset_cache()


def test_the_area_is_ordered_by_utilisation_not_resemblance(client):
    body = client.get("/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3").json()
    order = [p["cell_id"] for p in body["predictions"]]
    # Population drives utilisation here, so 900 outranks 400 outranks 20.
    assert order[0] == "JBDTBK_00003", "diurutkan pakai model deskriptif, bukan prediktif"
    assert order[:3] == ["JBDTBK_00003", "JBDTBK_00004", "JBDTBK_00002"]
    # ...and that is the exact reverse of the resemblance ordering.
    by_resemblance = [p["cell_id"] for p in
                      sorted(body["predictions"], key=lambda x: -x["probability"])]
    assert by_resemblance[0] == "JBDTBK_00001"


def test_every_prediction_carries_a_utilisation_number(client):
    body = client.get("/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3").json()
    top = body["predictions"][0]
    assert top["sessions_per_connector_day"] == pytest.approx(900.0 + 20.0, rel=1e-4)


def test_the_summary_covers_unbuilt_cells_only(client):
    d = client.get(
        "/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3").json()["distribution"]
    # Cell 1 holds two stations and is excluded; 20, 400 and 900 remain.
    assert d["max_sessions_per_connector_day"] == pytest.approx(920.0, rel=1e-4)
    assert d["median_sessions_per_connector_day"] == pytest.approx(420.0, rel=1e-4)
    assert d["cells_with_station"] == 1


def test_provenance_says_scenario_and_carries_the_window(client):
    m = client.get(
        "/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3").json()["utilisation_model"]
    assert "SCENARIO" in m["label"]
    assert m["window_days"] == 3 and m["dose_response"] == pytest.approx(1.64)
    assert m["reference_spec"] == SPEC


def test_specific_cells_endpoint_carries_utilisation_too(client):
    body = client.post("/api/v1/planner/predict",
                       json={"cell_ids": ["JBDTBK_00003"]}).json()
    assert body["predictions"][0]["sessions_per_connector_day"] == pytest.approx(920.0, rel=1e-4)
    assert body["utilisation_model"]["window_days"] == 3


def test_a_missing_artifact_leaves_the_descriptive_answer_standing(client, monkeypatch, tmp_path):
    # An addition that can fail must fail quietly enough to leave the rest up.
    # Taking the endpoint down because the second model is absent would turn an
    # added capability into an outage.
    monkeypatch.setattr(utilisation_model, "DEFAULT_MODEL_PATH", str(tmp_path / "gone.joblib"))
    utilisation_model.reset_cache()
    r = client.get("/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3")
    assert r.status_code == 200
    body = r.json()
    assert body["utilisation_model"] is None
    assert all(p["sessions_per_connector_day"] is None for p in body["predictions"])
    # Falls back to the old resemblance ordering rather than to an arbitrary one.
    assert [p["cell_id"] for p in body["predictions"]][0] == "JBDTBK_00001"


# --- suitability, as the area endpoint serves it ------------------------------

def test_every_prediction_carries_a_band_and_the_scale_that_made_it(client):
    body = client.get("/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3").json()
    for p in body["predictions"]:
        assert p["suitability"] is not None and 0.0 <= p["suitability"] <= 1.0
        assert p["suitability_band"] in ("red", "yellow", "green")
        assert p["supply_discount"] is not None
    scale = body["distribution"]["suitability_scale"]
    # The legend prints these, so they travel with the shading rather than being
    # remembered: a retrain moves the floors and a stale constant would quietly
    # band cells against the wrong distribution.
    assert scale["yellow_floor"] <= scale["red_floor"]
    assert scale["cells_scored"] > 0
    counted = sum(body["distribution"][k] for k in ("cells_red", "cells_yellow", "cells_green"))
    assert counted == body["distribution"]["cells_without_station"]


def test_a_crowded_cell_cannot_outrank_an_empty_one_with_the_same_demand(monkeypatch, artifact):
    """AC (c), through the endpoint rather than the formula.

    Same population, so the model predicts the same demand; the only difference
    is four stations already inside 2 km. The supply half of the blend has to be
    what separates them, or the shortlist will point at a place already served.
    """
    from api import planner_repo
    from api.main import app, require_planner
    from api.services import resemblance_scale, siting_model, utilisation_model
    from fastapi.testclient import TestClient

    cells = [_cell(1, 500.0, stations_2km=0, nearest_m=9000.0),
             _cell(2, 500.0, stations_2km=4, nearest_m=200.0)]
    monkeypatch.setattr(planner_repo, "features_in_radius",
                        lambda *a, **k: (cells, len(cells)))
    monkeypatch.setattr(planner_repo, "features_for_unbuilt_cells", lambda names, **kw: cells)
    monkeypatch.setattr(planner_repo, "features_for_scoring", lambda names, **kw: cells)
    monkeypatch.setattr(planner_repo, "supply_fingerprint", lambda: "test/fixture")
    monkeypatch.setattr(siting_model, "info", lambda path=None: _SitingInfo())
    monkeypatch.setattr(siting_model, "predict", lambda rows, path=None: [0.5] * len(rows))
    monkeypatch.setattr(utilisation_model, "DEFAULT_MODEL_PATH", artifact)
    resemblance_scale.reset_cache()
    app.dependency_overrides[require_planner] = lambda: {"id": "u",
                                                         "account_type": "business_planner"}
    try:
        body = TestClient(app).get(
            "/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3").json()
    finally:
        app.dependency_overrides.pop(require_planner, None)
        resemblance_scale.reset_cache()

    by_id = {p["cell_id"]: p for p in body["predictions"]}
    empty, crowded = by_id["JBDTBK_00001"], by_id["JBDTBK_00002"]
    assert empty["sessions_per_connector_day"] == crowded["sessions_per_connector_day"]
    assert empty["suitability"] > crowded["suitability"]
    assert crowded["supply_discount"] < empty["supply_discount"]


def test_a_database_failure_leaves_the_rest_of_the_answer_standing(client, monkeypatch):
    """The scale needs the database; the answer around it does not.

    A narrower catch let an OperationalError out of the scale build and 500'd the
    whole endpoint over an enrichment, taking the resemblance figures, the cell
    split and the geometry with it.
    """
    from api import planner_repo

    def boom(*a, **k):
        raise RuntimeError("database is down")

    monkeypatch.setattr(planner_repo, "supply_fingerprint", boom)
    r = client.get("/api/v1/planner/predict.area?lat=-6.17&lon=106.82&radius_km=3")
    assert r.status_code == 200
    body = r.json()
    assert body["distribution"]["suitability_scale"] is None
    assert all(p["suitability_band"] is None for p in body["predictions"])
    # The half that never needed the scale is untouched.
    assert body["distribution"]["cells_predicted"] > 0
    assert all(p["probability"] is not None for p in body["predictions"])
