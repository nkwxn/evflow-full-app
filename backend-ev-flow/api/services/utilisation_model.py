"""Serve the trained utilisation model -- the prescriptive one.

Fitted offline by ev-planner-study/train_utilisation_model.py. This module loads
it once and answers predictions, exactly as services/siting_model does, and for
the same reason: scikit-learn predicts on positional arrays, so `feature_names`
travels inside the artifact and every call is assembled from a dict, by name.

HOW THIS DIFFERS FROM THE SITING MODEL, AND WHY BOTH EXIST

The siting model answers "does this cell resemble the ones that already have a
station". Measured on the full grid, its 500 highest-probability cells are 100%
cells that already have one, so it cannot rank a place nobody has built on.

This one predicts sessions per connector per day. It CAN rank unbuilt cells,
which is the planner's actual question, so it drives the ordering while the
resemblance figure stays alongside as context.

THE HARDWARE SPLIT, WHICH IS THE ONE THING A CALLER MUST UNDERSTAND

The model was trained with two features a planning cell does not have:
`connectors` and `avg_kw`. They are not properties of a place, they are what the
planner chooses to build there, and the training measured them carrying 57% of
the model's importance -- charger power alone dominates how many sessions a
connector turns over, because a faster charger finishes sooner and takes the next
car.

So a prediction is always "a site of THIS spec, at THIS place". Scoring the grid
holds the spec at the artifact's reference_spec, the median of what is actually
built, which is what makes cells comparable to each other: every difference that
remains is location. `location_features` is what the caller must fetch from
planning_cells; the hardware columns are injected here and must NOT be asked of
the database, which does not have them.

WHAT THE NUMBER IS, AND IS NOT

It is a SCENARIO. Every session it learned from is simulation output, and that
simulation weights each station by 0.53*rank(population) + 0.30*rank(poi_total)
+ 0.17*rank(road_nodes). The model recovers that assumption; it does not discover
demand. Measured at the reference spec its predictions spread 1.66x across the
grid against the simulation's own 1.64x, and rank at Spearman +0.61 against that
blend -- a consistency check, not evidence about the world. Say SCENARIO wherever
the number surfaces.

Quote loco_r2 with its caveat: it scores the training target, hardware variation
included, so it is not a measure of place-ranking skill. The 1.66x spread is.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import joblib

#: Where train_utilisation_model.py writes the artifact. Overridable so a
#: deployment can mount it elsewhere without a code change.
DEFAULT_MODEL_PATH = os.getenv(
    "UTILISATION_MODEL_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "..", "ev-planner-study", "output",
        "utilisation_model.joblib"),
)

_cache: Dict[str, dict] = {}


@dataclass(frozen=True)
class UtilisationInfo:
    """What the API can say about the model behind a utilisation number.

    Carried into every response that quotes one. A figure in sessions per day
    reads as a measurement unless its provenance travels with it, and this one
    is a scenario recovered from an assumption.
    """
    trained_at: str
    n_samples: int
    loco_r2: float
    random_split_r2: float
    label: str
    target: str
    target_units: str
    sklearn_version: str
    feature_names: List[str]
    location_features: List[str]
    reference_spec: Dict[str, float]
    window_start: str
    window_end: str
    window_days: int
    dose_response: float
    median_sessions_per_cell: Optional[float]
    counting_noise_pct: Optional[float]


def reset_cache() -> None:
    """Drop the loaded artifact. For tests, and for reloading after a retrain."""
    _cache.clear()


def _load(path: Optional[str] = None) -> dict:
    key = os.path.abspath(path or DEFAULT_MODEL_PATH)
    if key in _cache:
        return _cache[key]
    if not os.path.exists(key):
        raise FileNotFoundError(
            f"no utilisation model at {key}. Build one with "
            f"ev-planner-study/train_utilisation_model.py, or point "
            f"UTILISATION_MODEL_PATH at an existing artifact.")
    _cache[key] = joblib.load(key)
    return _cache[key]


def info(path: Optional[str] = None) -> UtilisationInfo:
    a = _load(path)
    spec = dict(a.get("reference_spec") or {})
    names = list(a["feature_names"])
    return UtilisationInfo(
        trained_at=a["trained_at"], n_samples=a["n_samples"],
        loco_r2=a["loco_r2"], random_split_r2=a["random_split_r2"],
        label=a["label"], target=a["target"], target_units=a["target_units"],
        sklearn_version=a["sklearn_version"],
        feature_names=names,
        # The caller fetches these from planning_cells. The hardware columns are
        # deliberately absent: the table does not have them and asking for them
        # trips the repo's staleness check.
        location_features=[n for n in names if n not in spec],
        reference_spec=spec,
        window_start=a["window_start"], window_end=a["window_end"],
        window_days=a["window_days"], dose_response=a["dose_response_q4_over_q1"],
        median_sessions_per_cell=a.get("median_sessions_per_cell"),
        counting_noise_pct=a.get("counting_noise_pct"),
    )


def predict(rows: Sequence[Dict[str, Any]], spec: Optional[Dict[str, float]] = None,
            path: Optional[str] = None) -> List[float]:
    """Sessions per connector per day for each row, at a fixed hardware spec.

    Rows carry LOCATION features only, keyed by name. The hardware features are
    filled from `spec`, defaulting to the artifact's reference spec, because they
    describe the site a planner would build rather than the place itself. A row
    that supplies them anyway is an error: silently preferring one source over
    the other is how two callers end up comparing cells at different specs
    without either of them knowing.
    """
    if not rows:
        return []

    artifact = _load(path)
    names: List[str] = list(artifact["feature_names"])
    hardware = dict(artifact.get("reference_spec") or {})
    if spec:
        unknown = set(spec) - set(hardware)
        if unknown:
            raise ValueError(
                f"spec has {len(unknown)} key(s) the model has no feature for: "
                f"{', '.join(sorted(unknown))}")
        hardware.update({k: float(v) for k, v in spec.items()})

    expected = set(names) - set(hardware)

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
            supplied = extra & set(hardware)
            if supplied:
                raise ValueError(
                    f"row {i} supplies hardware feature(s) {', '.join(sorted(supplied))}; "
                    f"pass them in spec= instead so every row is scored at one spec")
            raise ValueError(
                f"row {i} has unexpected feature(s) the model was not trained on: "
                f"{', '.join(sorted(extra))}")
        values = []
        for name in names:  # artifact order, not dict order
            v = float(hardware[name] if name in hardware else row[name])
            if not math.isfinite(v):
                raise ValueError(f"row {i} feature '{name}' must be finite, got {v}")
            values.append(v)
        matrix.append(values)

    return [float(v) for v in artifact["model"].predict(matrix)]
