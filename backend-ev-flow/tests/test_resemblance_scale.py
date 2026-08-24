"""The ceiling an unbuilt cell's score is read against.

It replaced a constant in the frontend, EMPTY_CELL_CEILING = 0.31. The constant
was correct when written and had no way to stay correct: the ceiling depends on
the model and the grid, migration 0022 says the POI expansion means the model
needs retraining, and a retrained model would leave the dashboard quoting a
percentage of the wrong denominator with nothing raising an error.
"""
import pytest

from api.services import resemblance_scale


@pytest.fixture(autouse=True)
def clean():
    resemblance_scale.reset_cache()
    yield
    resemblance_scale.reset_cache()


def test_the_ceiling_is_the_highest_any_unbuilt_cell_reaches():
    scale = resemblance_scale.unbuilt_ceiling(
        "2026-08-22T00:00:00", lambda: [{}, {}, {}], lambda rows: [0.01, 0.305, 0.12])
    assert scale.ceiling == 0.305
    assert scale.cells_scored == 3


def test_it_is_computed_once_and_kept():
    # One query plus one inference pass over 26,334 cells, about 165 ms. Paying
    # that on every area request would dominate a request that otherwise takes
    # 17 to 42 ms.
    calls = {"load": 0, "predict": 0}

    def load():
        calls["load"] += 1
        return [{}, {}]

    def predict(rows):
        calls["predict"] += 1
        return [0.1, 0.2]

    for _ in range(5):
        resemblance_scale.unbuilt_ceiling("2026-08-22T00:00:00", load, predict)
    assert calls == {"load": 1, "predict": 1}


def test_a_retrained_model_gets_its_own_ceiling():
    # THE reason this is not a constant. Two models have two ceilings, and
    # quoting one against the other is the failure being replaced.
    first = resemblance_scale.unbuilt_ceiling(
        "2026-08-22T00:00:00", lambda: [{}], lambda rows: [0.305])
    second = resemblance_scale.unbuilt_ceiling(
        "2026-09-01T00:00:00", lambda: [{}], lambda rows: [0.480])
    assert first.ceiling == 0.305
    assert second.ceiling == 0.480


def test_no_unbuilt_cells_is_an_error_not_a_ceiling_of_zero():
    # Zero would divide into every score as 100%, so the weakest cell in the
    # region would read as the best possible one.
    with pytest.raises(ValueError, match="no unbuilt cells"):
        resemblance_scale.unbuilt_ceiling("t", lambda: [], lambda rows: [])


def test_a_model_that_returns_nothing_is_an_error_too():
    with pytest.raises(ValueError, match="no probabilities"):
        resemblance_scale.unbuilt_ceiling("t", lambda: [{}], lambda rows: [])


def test_the_cache_can_be_dropped_after_a_poi_reload():
    # A POI reload changes the features under an unchanged model, so trained_at
    # does not move and the cache would otherwise serve a stale ceiling. The
    # documented fix is a restart; reset_cache is what makes that testable and
    # gives a process another way out.
    resemblance_scale.unbuilt_ceiling("t", lambda: [{}], lambda rows: [0.20])
    resemblance_scale.reset_cache()
    again = resemblance_scale.unbuilt_ceiling("t", lambda: [{}], lambda rows: [0.40])
    assert again.ceiling == 0.40
