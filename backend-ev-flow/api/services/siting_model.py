"""Serve the trained siting model.

The model is fitted offline by ev-planner-study/train_siting_model.py and saved
as a joblib artifact. This module loads it once and answers predictions.

WHY THE FEATURE ORDER LIVES IN THE ARTIFACT

scikit-learn predicts on positional arrays. Give it the right numbers in the
wrong column order and it returns confident, well-formed, entirely wrong
probabilities: no exception, no warning, `population` simply read as
`road_length_m`. Nothing downstream can detect that, and the output looks
exactly like a working model. So `feature_names` is saved with the estimator and
every call is built in that order, from a dict, by name.

WHAT THE MODEL ACTUALLY PREDICTS

P(a cell contains a station), learned from the existing network. That network is
1,080 PLN placements out of 1,236, following PLN offices and policy targets, so
this is descriptive of where stations ARE rather than prescriptive about where
they SHOULD be. The API surfaces it alongside the weighted score rather than in
place of it, and labels it, because a planner reading a single number has no way
to know which of the two questions it answered.

Leave-one-area-out AUC is 0.801, and that is the number worth quoting. The
random-split figure of 0.927 is inflated: neighbouring cells land on both sides
of the split, so the model is largely recalling answers from a few hundred
metres away rather than generalising to a new area.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import joblib

#: Where train_siting_model.py writes the artifact. Overridable so a deployment
#: can mount it somewhere else without a code change.
DEFAULT_MODEL_PATH = os.getenv(
    "SITING_MODEL_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "..", "ev-planner-study", "output", "siting_model.joblib"),
)

_cache: Dict[str, dict] = {}


@dataclass(frozen=True)
class ModelInfo:
    """What the API can say about the model behind a prediction.

    Carried into every response. A probability with no provenance is a number
    nobody can audit, and this one needs its caveat travelling with it.
    """
    trained_at: str
    n_samples: int
    n_positive: int
    loco_auc: float
    random_split_auc: float
    label: str
    sklearn_version: str
    feature_names: List[str]


def reset_cache() -> None:
    """Drop the loaded artifact. For tests, and for reloading after a retrain."""
    _cache.clear()


def _load(path: Optional[str] = None) -> dict:
    key = os.path.abspath(path or DEFAULT_MODEL_PATH)
    if key in _cache:
        return _cache[key]
    if not os.path.exists(key):
        raise FileNotFoundError(
            f"no siting model at {key}. Build one with "
            f"ev-planner-study/train_siting_model.py, or point SITING_MODEL_PATH "
            f"at an existing artifact.")
    artifact = joblib.load(key)
    _cache[key] = artifact
    return artifact


def info(path: Optional[str] = None) -> ModelInfo:
    a = _load(path)
    return ModelInfo(
        trained_at=a["trained_at"], n_samples=a["n_samples"],
        n_positive=a["n_positive"], loco_auc=a["loco_auc"],
        random_split_auc=a["random_split_auc"], label=a["label"],
        sklearn_version=a["sklearn_version"], feature_names=list(a["feature_names"]),
    )


def predict(rows: Sequence[Dict[str, Any]], path: Optional[str] = None) -> List[float]:
    """P(station) for each row, built in the artifact's feature order.

    Rows are dicts keyed by feature name. They are never passed through
    positionally: see the module docstring for why that distinction is the whole
    point of this function.
    """
    if not rows:
        return []

    artifact = _load(path)
    names: List[str] = list(artifact["feature_names"])
    expected = set(names)

    matrix = []
    for i, row in enumerate(rows):
        got = set(row)
        missing = expected - got
        if missing:
            # Not filled with zero: zero population is a meaningful value, so a
            # defaulted gap answers a question about a place that does not exist.
            raise ValueError(
                f"row {i} is missing {len(missing)} feature(s): {', '.join(sorted(missing))}")
        extra = got - expected
        if extra:
            raise ValueError(
                f"row {i} has unexpected feature(s) the model was not trained on: "
                f"{', '.join(sorted(extra))}")
        values = []
        for name in names:  # artifact order, not dict order
            v = float(row[name])
            if not math.isfinite(v):
                raise ValueError(f"row {i} feature '{name}' must be finite, got {v}")
            values.append(v)
        matrix.append(values)

    proba = artifact["model"].predict_proba(matrix)
    return [float(p[1]) for p in proba]
