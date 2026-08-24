"""Serving a model is mostly about refusing to serve it wrongly.

scikit-learn predicts on positional arrays. Hand it the same numbers in a
different column order and it returns confident, well-formed, silently wrong
probabilities: no exception, no warning, population simply read as road length.
Nothing downstream can detect that. So the feature order travels inside the
artifact and is checked on every call, and most of these tests are about the
refusals rather than the arithmetic.
"""
import numpy as np
import pytest

from api.services import siting_model


class _Stub:
    """Stands in for a fitted estimator; returns the first feature as P(class 1)."""

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        p = np.clip(X[:, 0], 0, 1)
        return np.column_stack([1 - p, p])


@pytest.fixture
def artifact(tmp_path):
    import joblib
    path = tmp_path / "m.joblib"
    joblib.dump({
        "model": _Stub(),
        "feature_names": ["alpha", "beta", "gamma"],
        "trained_at": "2026-08-22T00:00:00+00:00",
        "n_samples": 27219, "n_positive": 885,
        "loco_auc": 0.801, "random_split_auc": 0.927,
        "label": "station presence", "sklearn_version": "1.7.2",
    }, path)
    siting_model.reset_cache()
    yield str(path)
    siting_model.reset_cache()


def test_a_loaded_model_reports_what_it_is(artifact):
    # A prediction with no provenance is a number nobody can audit. The API has
    # to be able to say which model produced it and how well it scored.
    info = siting_model.info(artifact)
    assert info.loco_auc == 0.801
    assert info.n_samples == 27219
    assert info.feature_names == ["alpha", "beta", "gamma"]


def test_predictions_are_probabilities(artifact):
    out = siting_model.predict([{"alpha": 0.25, "beta": 9, "gamma": 9}], artifact)
    assert len(out) == 1
    assert 0.0 <= out[0] <= 1.0
    assert out[0] == pytest.approx(0.25)


def test_features_are_ordered_by_the_artifact_not_by_the_caller(artifact):
    # The dict below is deliberately in the wrong order. If the service passed
    # dict order straight through, alpha would land in gamma's slot and the
    # answer would be 9 clipped to 1.0 rather than 0.25.
    out = siting_model.predict([{"gamma": 9, "beta": 9, "alpha": 0.25}], artifact)
    assert out[0] == pytest.approx(0.25)


def test_a_missing_feature_is_refused_rather_than_defaulted(artifact):
    # Filling a gap with zero is the tempting fix and the wrong one: zero
    # population is a meaningful value, so the model would answer a question
    # about a place that does not exist.
    with pytest.raises(ValueError, match="missing"):
        siting_model.predict([{"alpha": 1, "beta": 2}], artifact)


def test_an_unexpected_feature_is_refused(artifact):
    # Extra columns mean the caller is working from a different schema than the
    # model was trained on, which is exactly when the order check matters most.
    with pytest.raises(ValueError, match="unexpected"):
        siting_model.predict([{"alpha": 1, "beta": 2, "gamma": 3, "delta": 4}], artifact)


def test_non_finite_input_is_refused(artifact):
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite"):
            siting_model.predict([{"alpha": bad, "beta": 1, "gamma": 1}], artifact)


def test_a_missing_artifact_says_so_plainly(tmp_path):
    siting_model.reset_cache()
    with pytest.raises(FileNotFoundError, match="train_siting_model"):
        siting_model.info(str(tmp_path / "nope.joblib"))


def test_an_empty_batch_returns_nothing_rather_than_erroring(artifact):
    assert siting_model.predict([], artifact) == []


def test_the_artifact_is_loaded_once_not_per_request(artifact, monkeypatch):
    # A 6 MB joblib load on every request would dominate the response time.
    calls = {"n": 0}
    real = siting_model.joblib.load

    def counted(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(siting_model.joblib, "load", counted)
    siting_model.reset_cache()
    siting_model.predict([{"alpha": 1, "beta": 1, "gamma": 1}], artifact)
    siting_model.predict([{"alpha": 1, "beta": 1, "gamma": 1}], artifact)
    siting_model.info(artifact)
    assert calls["n"] == 1
