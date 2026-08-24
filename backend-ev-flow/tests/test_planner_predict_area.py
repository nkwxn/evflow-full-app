"""On-demand scoring around a point the planner picked.

Two invariants carry most of these tests, and both exist because an earlier
version of this endpoint got them wrong in ways nothing flagged.

ONE. An area is scored CELL BY CELL, never summed into a single feature vector.
The model was fitted on 400 m cells; a 10 x 10 km selection pushes 18 of its 33
additive features past anything in the training set, and a random forest can only
repeat its most extreme leaves there. It answered 0.605 where the true per-cell
mean was 0.040.

TWO. Cells that ALREADY have a station are reported apart from those that do not.
Measured across all 27,219 cells: the model's top 500 are 100% cells that already
have one, and among the 26,334 with none the highest probability is 0.305, with
not one above 0.5. The endpoint used to report "cells above 0.5" as the
shortlist count, which in practice counted existing stations and offered them as
candidates.
"""
import pytest
from fastapi.testclient import TestClient

from api import planner_repo
from api.main import app, require_planner
from api.services import resemblance_scale, siting_model

BBOX = "106.78,-6.22,106.87,-6.13"
POINT = "lat=-6.175&lon=106.827&radius_km=3"
FEATURES = ["population", "road_length_m", "poi_mall"]


class _Info:
    trained_at = "2026-08-22T00:00:00+00:00"
    n_samples, n_positive = 27219, 885
    loco_auc, random_split_auc = 0.814, 0.927
    label, sklearn_version = "station presence", "1.7.2"
    feature_names = FEATURES


def _cell(i, mall, stations=0):
    return {"cell_id": f"JBDTBK_{i:05d}", "kota": "Jakarta Pusat", "station_count": stations,
            "population": 100 * i, "road_length_m": 500.0 * i, "poi_mall": mall}


@pytest.fixture
def calls():
    return {}


@pytest.fixture
def client(monkeypatch, calls):
    # Two cells already hold a station and score highest, exactly as the real
    # model behaves. A summary that ignores that reports them as candidates.
    cells = [_cell(1, 0.95, stations=2), _cell(2, 0.90, stations=1),
             _cell(3, 0.30), _cell(4, 0.10), _cell(5, 0.20)]

    def _area(viewport, names, limit=30000, **kw):
        calls["mode"] = "bbox"; calls["names"] = list(names); calls["limit"] = limit
        return cells[:limit], len(cells)

    def _radius(lat, lon, radius_km, names, limit=30000, **kw):
        calls["mode"] = "radius"; calls["centre"] = (lat, lon); calls["radius"] = radius_km
        calls["names"] = list(names); calls["limit"] = limit
        return cells[:limit], len(cells)

    def _predict(rows, path=None):
        # Called twice now: once for the cells in the circle, once for the
        # region-wide unbuilt cells the ceiling is taken over. Recorded apart so
        # the second cannot quietly overwrite what the first was asked.
        seen = [dict(r) for r in rows]
        calls.setdefault("predict_calls", []).append(seen)
        calls["rows"] = calls["predict_calls"][0]
        return [float(r["poi_mall"]) for r in rows]

    # The region-wide unbuilt population the resemblance ceiling is taken over.
    # Its best cell scores 0.30, so a local best of 0.30 is 100% of the ceiling
    # and anything lower is a readable fraction of it.
    def _unbuilt(names, **kw):
        calls["unbuilt_names"] = list(names)
        return [_cell(9, 0.30), _cell(10, 0.05), _cell(11, 0.01)]

    monkeypatch.setattr(planner_repo, "features_in_area", _area)
    monkeypatch.setattr(planner_repo, "features_in_radius", _radius)
    monkeypatch.setattr(planner_repo, "features_for_unbuilt_cells", _unbuilt)
    # Module-level cache, so without this one test's ceiling leaks into the next.
    resemblance_scale.reset_cache()
    monkeypatch.setattr(siting_model, "predict", _predict)
    monkeypatch.setattr(siting_model, "info", lambda path=None: _Info())
    app.dependency_overrides[require_planner] = lambda: {"id": "u", "account_type": "business_planner"}
    yield TestClient(app)
    app.dependency_overrides.pop(require_planner, None)
    resemblance_scale.reset_cache()


# --- invarian satu: per sel, bukan agregat -------------------------------------

def test_every_cell_is_scored_on_its_own(client, calls):
    r = client.get(f"/api/v1/planner/predict.area?{POINT}")
    assert r.status_code == 200
    assert len(calls["rows"]) == 5, "area dijumlahkan jadi satu baris"
    assert len(r.json()["predictions"]) == 5


def test_the_response_carries_no_single_area_probability(client):
    body = client.get(f"/api/v1/planner/predict.area?{POINT}").json()
    for banned in ("probability", "area_probability", "score"):
        assert banned not in body, f"'{banned}' di akar respons adalah angka ekstrapolasi"


def test_only_the_models_own_features_reach_it(client, calls):
    # station_count travels with the row for the response, and must NOT reach the
    # model: siting_model rejects unknown features rather than guessing.
    client.get(f"/api/v1/planner/predict.area?{POINT}")
    assert set(calls["rows"][0]) == set(FEATURES)
    assert "station_count" not in calls["rows"][0]


# --- invarian dua: SPKLU yang sudah ada dipisahkan ------------------------------

def test_existing_stations_are_flagged_not_hidden(client):
    # They stay in the list, because seeing that the top of the ranking is
    # already built IS the finding. They just must not be mistakable for
    # candidates.
    preds = client.get(f"/api/v1/planner/predict.area?{POINT}").json()["predictions"]
    assert [p["has_station"] for p in preds[:2]] == [True, True]
    assert all(p["has_station"] is False for p in preds[2:])


def test_the_summary_describes_only_cells_that_could_be_built_on(client):
    # Empty cells here are 0.30, 0.20, 0.10. Including the two built cells
    # (0.95, 0.90) would put the mean at 0.49 and the max at 0.95, which is the
    # bug this replaced: it read as a strong area when nothing buildable in it
    # scores above 0.30.
    d = client.get(f"/api/v1/planner/predict.area?{POINT}").json()["distribution"]
    assert d["cells_with_station"] == 2
    assert d["cells_without_station"] == 3
    assert d["max_probability"] == pytest.approx(0.30)
    assert d["median_probability"] == pytest.approx(0.20)
    assert d["mean_probability"] == pytest.approx(0.20)


def test_there_is_no_above_half_shortlist_count(client):
    # Measured on the full grid, no cell without a station reaches 0.5. A count
    # against that threshold was only ever counting existing stations.
    d = client.get(f"/api/v1/planner/predict.area?{POINT}").json()["distribution"]
    assert "cells_above_half" not in d


def test_an_area_that_is_already_fully_built_reports_null_not_zero(monkeypatch, client):
    # Zero would read as "measured, and nothing resembles a site". Null reads as
    # "there is nothing here left to measure", which is the true statement.
    monkeypatch.setattr(planner_repo, "features_in_radius",
                        lambda *a, **k: ([_cell(1, 0.9, stations=1)], 1))
    d = client.get(f"/api/v1/planner/predict.area?{POINT}").json()["distribution"]
    assert d["cells_without_station"] == 0
    assert d["max_probability"] is None
    assert d["mean_probability"] is None
    assert d["median_probability"] is None


# --- area berbentuk lingkaran ---------------------------------------------------

def test_a_point_and_radius_reach_the_circle_query(client, calls):
    client.get(f"/api/v1/planner/predict.area?{POINT}")
    assert calls["mode"] == "radius"
    assert calls["centre"] == (-6.175, 106.827)
    assert calls["radius"] == 3.0


def test_a_bbox_still_works_for_callers_that_want_one(client, calls):
    client.get(f"/api/v1/planner/predict.area?bbox={BBOX}")
    assert calls["mode"] == "bbox"


def test_giving_both_forms_is_refused_rather_than_silently_picking_one(client):
    # Silently preferring one would answer a question about an area the caller
    # did not ask about, and the response carries nothing that would show it.
    assert client.get(
        f"/api/v1/planner/predict.area?{POINT}&bbox={BBOX}").status_code == 422


def test_giving_neither_form_is_refused(client):
    assert client.get("/api/v1/planner/predict.area").status_code == 422


def test_half_a_point_is_refused(client):
    assert client.get("/api/v1/planner/predict.area?lat=-6.175").status_code == 422


def test_an_absurd_radius_is_refused(client):
    # Past 25 km a circle stops describing one place.
    assert client.get(
        "/api/v1/planner/predict.area?lat=-6.175&lon=106.827&radius_km=500").status_code == 422


# --- pelaporan dan kegagalan ----------------------------------------------------

def test_predictions_come_back_highest_first(client):
    p = [x["probability"] for x in
         client.get(f"/api/v1/planner/predict.area?{POINT}").json()["predictions"]]
    assert p == sorted(p, reverse=True)


def test_the_distribution_covers_every_scored_cell_not_the_trimmed_list(client):
    d = client.get(f"/api/v1/planner/predict.area?{POINT}&top=1").json()
    assert len(d["predictions"]) == 1
    assert d["distribution"]["cells_predicted"] == 5
    assert d["distribution"]["cells_without_station"] == 3


def test_a_clipped_area_says_so_and_reports_its_real_size(client):
    d = client.get(f"/api/v1/planner/predict.area?{POINT}&limit=2").json()["distribution"]
    assert d["cells_predicted"] == 2
    assert d["cells_in_area"] == 5
    assert d["truncated"] is True


def test_the_map_layers_draw_limit_is_accepted(client):
    # The map draws DRAW_LIMIT cells (site-prediction/areaPrediction.ts). Shipped
    # once with this ceiling at 4,000 while the map asked for 6,000: every test
    # and the typecheck passed while the dashboard showed only the validation
    # error. The two limits live in different languages, so they meet here.
    assert client.get(f"/api/v1/planner/predict.area?{POINT}&top=6000").status_code == 200


def test_the_caveat_and_provenance_travel_with_the_numbers(client):
    body = client.get(f"/api/v1/planner/predict.area?{POINT}").json()
    assert body["model"]["loco_auc"] == 0.814
    assert body["interpretation"].strip()


def test_a_malformed_bbox_is_refused(client):
    assert client.get("/api/v1/planner/predict.area?bbox=106.8,-6.2").status_code == 422


def test_an_empty_area_is_not_reported_as_a_zero_score(monkeypatch, client):
    monkeypatch.setattr(planner_repo, "features_in_radius", lambda *a, **k: ([], 0))
    assert client.get(f"/api/v1/planner/predict.area?{POINT}").status_code == 404


def test_a_missing_model_is_a_503_not_a_guess(monkeypatch, client):
    def _boom(path=None):
        raise FileNotFoundError("no siting model at output/siting_model.joblib")
    monkeypatch.setattr(siting_model, "info", _boom)
    r = client.get(f"/api/v1/planner/predict.area?{POINT}")
    assert r.status_code == 503
    assert "siting_model" in r.json()["detail"]


def test_a_model_stale_against_the_schema_is_a_503(monkeypatch, client):
    def _stale(*a, **k):
        raise ValueError("the model expects 2 column(s) planning_cells does not have")
    monkeypatch.setattr(planner_repo, "features_in_radius", _stale)
    assert client.get(f"/api/v1/planner/predict.area?{POINT}").status_code == 503


# --- skala yang membuat angkanya terbaca ------------------------------------

def test_the_response_carries_the_ceiling_rather_than_leaving_it_to_the_client(client):
    # It used to be EMPTY_CELL_CEILING = 0.31 in the frontend. Correct when
    # written, and with no way to stay correct: the ceiling depends on the model,
    # and migration 0022 says the POI expansion means the model needs retraining.
    # A retrain would leave the dashboard quoting a percentage of the wrong
    # denominator with nothing raising an error.
    d = client.get(f"/api/v1/planner/predict.area?{POINT}").json()["distribution"]
    assert d["resemblance_ceiling"] == pytest.approx(0.30)
    assert d["resemblance_ceiling_cells"] == 3


def test_the_ceiling_comes_from_unbuilt_cells_only(client, calls):
    # Built cells are what the model scores highest, so including them would put
    # the ceiling near 1.0 and make every real candidate look worthless.
    client.get(f"/api/v1/planner/predict.area?{POINT}")
    assert calls["unbuilt_names"] == FEATURES


def test_a_missing_ceiling_does_not_take_the_whole_answer_with_it(monkeypatch, client):
    # The per-cell probabilities are still valid without a scale to read them
    # against. The client is told there is none and must omit the comparison.
    def _boom(*a, **k):
        raise ValueError("no unbuilt cells to derive a resemblance ceiling from")
    monkeypatch.setattr(planner_repo, "features_for_unbuilt_cells", _boom)
    r = client.get(f"/api/v1/planner/predict.area?{POINT}")
    assert r.status_code == 200
    d = r.json()["distribution"]
    assert d["resemblance_ceiling"] is None
    assert d["max_probability"] == pytest.approx(0.30)


def test_the_local_best_is_never_reported_above_the_regional_ceiling(client):
    # If it were, the card would say something scores more than the most anything
    # can score, which is the tell that the two came from different populations.
    d = client.get(f"/api/v1/planner/predict.area?{POINT}").json()["distribution"]
    assert d["max_probability"] <= d["resemblance_ceiling"] + 1e-9
