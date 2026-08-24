"""The ceiling that gives a resemblance score its scale.

WHY THIS EXISTS

The model's output for an unbuilt cell is a small number. Measured across all
26,334 cells in Jabodetabek with no station, the highest any of them reaches is
0.305, and the median is near zero. So 0.29 is not "29% likely", it is very
nearly the best score an unbuilt cell can get, and a planner shown 0.29 with no
scale reads it as poor.

WHY IT IS COMPUTED AND NOT WRITTEN DOWN

It was a constant in the frontend: EMPTY_CELL_CEILING = 0.31. That worked, and
it was a liability. The ceiling is a property of the model AND the grid, and
migration 0022 says in its own docstring that the POI expansion means the model
needs retraining. Retrain, and a hardcoded 0.31 keeps being quoted while the
real ceiling has moved, with nothing raising an error: the dashboard would
confidently print a percentage of the wrong denominator.

CACHING, AND WHAT THE CACHE DOES NOT CATCH

Scoring every unbuilt cell costs one query plus one inference pass, roughly
165 ms, so it is done once and kept. The key is the model's trained_at, which
means a retrain invalidates it correctly.

A POI reload does NOT invalidate it. That changes the features under a model
that has not been retrained, so the true ceiling moves while the cached one does
not. Detecting it would need a fingerprint query over the whole grid on every
request, measured at 37 ms against a 17 to 42 ms request, which is too much to
pay for an event that has happened once. Restart the API after reloading POI
data. This is stated rather than hidden because it is the same class of trap the
hardcoded constant was.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence


@dataclass(frozen=True)
class ResemblanceScale:
    """What an unbuilt cell's score should be read against."""
    ceiling: float
    cells_scored: int


_cache: Dict[str, ResemblanceScale] = {}


def reset_cache() -> None:
    """Drop the computed ceiling. For tests, and after a retrain or POI reload."""
    _cache.clear()


def unbuilt_ceiling(
    trained_at: str,
    load_rows: Callable[[], Sequence[dict]],
    predict: Callable[[Sequence[dict]], List[float]],
) -> ResemblanceScale:
    """Highest probability the model gives any cell with no station.

    Dependencies are injected rather than imported so this can be tested without
    a database or a fitted estimator. Keyed on trained_at: two different models
    have two different ceilings, and quoting one against the other is exactly the
    failure this replaces.
    """
    cached = _cache.get(trained_at)
    if cached is not None:
        return cached

    rows = load_rows()
    if not rows:
        # No unbuilt cells at all is not a ceiling of zero, it is the absence of
        # one. Zero would make every score read as 100% of the maximum.
        raise ValueError("no unbuilt cells to derive a resemblance ceiling from")

    probabilities = predict(rows)
    if not probabilities:
        raise ValueError("the model returned no probabilities for the unbuilt cells")

    scale = ResemblanceScale(ceiling=round(max(probabilities), 4), cells_scored=len(rows))
    _cache[trained_at] = scale
    return scale
