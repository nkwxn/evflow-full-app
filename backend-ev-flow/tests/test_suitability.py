"""The blend that decides what the heatmap paints.

Everything here is arithmetic over injected inputs: no database, no fitted
estimator. That is deliberate. The one property these have to guarantee -- that a
crowded place cannot reach the top decile -- is a claim about the formula, and a
test that needed a trained model to check it would be a test of the model.
"""
import pytest

from api.services import suitability as s


def _scale(model_weight=0.5, n=1000):
    """A synthetic region: utilisation 1..n, supply 0..9 cycling.

    Built through the real build_scale so the quantile machinery is under test
    rather than stubbed around.
    """
    rows = [{"u": float(i), "stations_2km": i % 10, "nearest_station_m": 5000.0}
            for i in range(1, n + 1)]
    return s.build_scale(
        trained_at="2026-08-27T00:00:00Z", supply_fingerprint="1197/3362", rows=rows,
        predict=lambda rs: [r["u"] for r in rs], location_features=["u"],
        model_weight=model_weight)


# --- the discount ------------------------------------------------------------

def test_an_unserved_cell_keeps_all_of_its_demand():
    d = s.supply_discount(0, None)
    assert d.discount == 1.0 and d.effective == 0.0


def test_a_missing_distance_means_unserved_not_zero_metres():
    """The single mistake that would invert the whole map.

    nearest_station_m is NULL only when there is no station to measure from.
    Coalescing it to 0 says "a station is exactly here" and gives an empty region
    the worst possible score everywhere -- which is what planner_repo's coverage
    rank did until it was found.
    """
    assert s.supply_discount(0, None).discount == 1.0
    assert s.supply_discount(0, 0.0).discount == pytest.approx(0.5)


def test_the_discount_falls_as_competitors_are_added():
    got = [s.supply_discount(n, 5000.0).discount for n in (0, 1, 3, 5)]
    assert got == sorted(got, reverse=True)
    assert got[0] == 1.0 and got[1] == pytest.approx(0.5) and got[3] == pytest.approx(1 / 6)


def test_a_station_in_the_same_car_park_counts_for_more_than_one_at_the_rim():
    """The double count is intentional, so a later reader does not 'fix' it."""
    close = s.supply_discount(1, 0.0)
    far = s.supply_discount(1, 1999.0)
    assert close.effective == pytest.approx(2.0)
    assert far.effective == pytest.approx(1.0005, abs=1e-3)
    assert close.discount < far.discount


def test_distance_beyond_the_radius_adds_nothing():
    # Past 2 km the fraction saturates; stations_2km is already counting whole
    # stations inside that radius, so anything further is not competition here.
    assert (s.supply_discount(0, 2000.0).effective
            == s.supply_discount(0, 50_000.0).effective == 0.0)


# --- the blend ---------------------------------------------------------------

def test_both_terms_move_the_result():
    scale = _scale()
    quiet_busy = s.score(900.0, 0, 5000.0, scale).suitability
    quiet_slow = s.score(100.0, 0, 5000.0, scale).suitability
    crowded_busy = s.score(900.0, 9, 5000.0, scale).suitability
    assert quiet_busy > quiet_slow, "the model term does nothing"
    assert quiet_busy > crowded_busy, "the supply term does nothing"


def test_the_top_decile_is_reserved_for_places_with_no_competitor():
    """AC (c), as the property that actually matters for a shortlist.

    The criterion says over-saturation is one reason a cell reads low. What a
    recommendation must never do is point at a place already crowded, so this
    checks the stronger direction: nothing with a competitor reaches red.
    """
    scale = _scale()
    crowded = [s.score(u, 9, 100.0, scale) for u in (100.0, 500.0, 900.0, 1000.0)]
    assert all(c.band != "red" for c in crowded), [c.band for c in crowded]


def test_the_bands_come_from_the_distribution_not_from_constants():
    scale = _scale()
    assert scale.yellow_floor <= scale.red_floor
    # Move the region and the floors move with it, which is the whole point of
    # deriving them: a retrain must not leave a threshold quoting a stale scale.
    other = _scale(n=200)
    assert (scale.red_floor, scale.yellow_floor) != (other.red_floor, other.yellow_floor) \
        or scale.cells_scored != other.cells_scored


def test_the_weight_decides_which_term_leads():
    model_led = s.score(1000.0, 9, 100.0, _scale(model_weight=0.9))
    supply_led = s.score(1000.0, 9, 100.0, _scale(model_weight=0.1))
    assert model_led.suitability > supply_led.suitability


def test_an_empty_region_raises_rather_than_scaling_against_nothing():
    with pytest.raises(ValueError, match="no cells"):
        s.build_scale("t", "f", [], lambda rs: [], ["u"])


# --- the cache ---------------------------------------------------------------

def test_a_retrain_and_a_supply_refresh_each_get_their_own_scale():
    s.reset_cache()
    calls = []

    def load():
        calls.append(1)
        return [{"u": float(i), "stations_2km": 0, "nearest_station_m": None}
                for i in range(1, 50)]

    args = (load, lambda rs: [r["u"] for r in rs], ["u"])
    s.cached_scale("model-A", "1197/3362", *args)
    s.cached_scale("model-A", "1197/3362", *args)
    assert len(calls) == 1, "the same model and supply should not rebuild"

    s.cached_scale("model-B", "1197/3362", *args)      # retrained
    s.cached_scale("model-A", "1240/3500", *args)      # stations imported
    assert len(calls) == 3
    s.reset_cache()
