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


def test_a_shortlist_cutoff_and_a_band_edge_come_from_the_same_table():
    scale = _scale()
    assert scale.quantile_at(0.90) == scale.red_floor
    assert scale.quantile_at(0.50) == scale.yellow_floor
    assert scale.quantile_at(0.0) <= scale.quantile_at(0.5) <= scale.quantile_at(1.0)
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError, match="quantile"):
            scale.quantile_at(bad)


# --- the shape of the real grid ----------------------------------------------

def _realistic_scale(model_weight=0.5, n=2000):
    """A region shaped like Jabodetabek, which _scale deliberately is not.

    _scale cycles supply 0..9 evenly, so every discount value is about as common
    as every other. The real grid is nothing like that: 65% of places have
    NOTHING within 2 km and sit at discount exactly 1.0, and central Jakarta
    carries a median of 25.

    That difference is not cosmetic. It is the entire mechanism behind the bug
    these tests cover, and the even fixture hides it completely -- both of the
    first two tests written here passed against _scale before the fix.
    """
    rows = []
    for i in range(1, n + 1):
        # 65% unserved, then a tail running out to the saturated core.
        supply = 0 if i % 100 < 65 else (i % 100) - 64
        rows.append({"u": float(i), "stations_2km": supply,
                     "nearest_station_m": 9000.0 if supply == 0 else 800.0})
    return s.build_scale(
        trained_at="2026-08-27T00:00:00Z", supply_fingerprint="1197/3362", rows=rows,
        predict=lambda rs: [r["u"] for r in rs], location_features=["u"],
        model_weight=model_weight)


def test_the_unserved_majority_really_does_tie_at_the_top():
    """The precondition for everything below. If this stops holding, the tests
    underneath stop testing what they claim to."""
    scale = _realistic_scale()
    assert scale.discount_q[500] == 1.0 and scale.discount_q[900] == 1.0


def test_a_place_with_two_competitors_can_still_beat_the_median():
    """The defect this guards against, measured on the real grid 2026-08-27.

    The discount used to be percentile-ranked before blending. With 65% of the
    grid tied at discount 1.0, that rank was a step function: 1.0 for the tie
    mass and at most 0.35 for everything else. Half the blend became a coin
    flip, and a place with two competitors could not exceed 0.624 even at a
    perfect demand rank -- below the 0.640 median floor. Moderately served
    districts flattened to one colour with no way to tell them apart.
    """
    scale = _realistic_scale()
    perfect = max(scale.utilisation_q)
    assert s.score(perfect, 2, 1500.0, scale).band in ("yellow", "red")


def test_the_discount_keeps_its_meaning_rather_than_its_rank():
    """1/(1+n) is a share of demand, not an ordering.

    One competitor leaves you half, four leave you a fifth: different by a
    factor of 2.5. A rank cannot express that when most of the grid is tied at
    the top, and squashing them into adjacent ranks is what threw the gradation
    away.
    """
    scale = _realistic_scale()
    mid = scale.utilisation_q[500]
    assert s.score(mid, 1, 9000.0, scale).suitability \
        - s.score(mid, 4, 9000.0, scale).suitability > 0.1


def test_a_saturated_place_stays_green_at_any_demand():
    """AC (c), which the fix must not cost. Measured on the grid: no place with
    four or more competitors reaches yellow, and central Jakarta runs to 58."""
    scale = _realistic_scale()
    perfect = max(scale.utilisation_q)
    for n in (4, 8, 25, 58):
        assert s.score(perfect, n, 200.0, scale).band == "green", f"{n} competitors"
