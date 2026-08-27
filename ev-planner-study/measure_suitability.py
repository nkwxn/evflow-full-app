"""Before building the suitability score, measure whether the ML term survives it.

THE DESIGN UNDER TEST

    U         = utilisation_model.predict(cell, reference_spec)   # ML, sessions/conn/day
    near      = clamp((2000 - min(nearest_station_m, 2000)) / 2000, 0, 1)
    supply    = stations_2km + near
    contested = U / (1 + supply)

1/(1+N) is the equal-attraction share: a new site among N incumbents takes
1/(1+N) of the catchment. Zero free parameters, which is why it was chosen over
an exponential decay whose k nobody could derive.

WHY THIS SCRIPT EXISTS RATHER THAN A COMMIT

The two terms have very different dynamic ranges. U spreads about 1.66x across
the grid; stations_2km runs from 0 to roughly 20, so 1/(1+supply) spreads about
20x. Multiplied naively the discount dominates by an order of magnitude and the
result is a competitor-count map wearing an ML label -- worse than what exists
now, because it would be wrong AND carry a claim of learning.

So the damping is a decision to be taken on evidence and written down, not a
constant to be picked. This prints what each term actually contributes.

Usage:
    DATABASE_URL="$(../.claude/skills/run-evflow/driver.sh url)" python3 measure_suitability.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend-ev-flow"))

SUPPLY_RADIUS_M = 2000.0


def spread(s) -> float:
    """p95 / p5. The measure the model's own docstring already quotes."""
    lo, hi = s.quantile(0.05), s.quantile(0.95)
    return float(hi / lo) if lo > 0 else float("inf")


def main() -> int:
    import numpy as np
    import pandas as pd
    from sqlalchemy import create_engine, text

    from api.services import utilisation_model

    url = os.getenv("DATABASE_URL")
    if not url:
        print('DATABASE_URL not set: DATABASE_URL="$(../.claude/skills/run-evflow/driver.sh url)"')
        return 2

    info = utilisation_model.info()
    cols = ", ".join(f'"{c}"' for c in info.location_features)
    engine = create_engine(url)
    with engine.connect() as c:
        df = pd.read_sql(text(f"""
            SELECT cell_id, {cols}, stations_2km, nearest_station_m, station_count
              FROM planning_cells
             WHERE overlap_frac >= 0.5 AND kota <> 'Kepulauan Seribu'
        """), c)
    print(f"cells scored            : {len(df):,}")
    print(f"reference spec          : {info.reference_spec}")

    rows = [{k: float(r[k]) for k in info.location_features} for _, r in df.iterrows()]
    df["U"] = utilisation_model.predict(rows)

    # NULL means no station exists to measure from, i.e. unserved -> near = 0.
    nearest = df["nearest_station_m"].fillna(SUPPLY_RADIUS_M).clip(upper=SUPPLY_RADIUS_M)
    df["near"] = ((SUPPLY_RADIUS_M - nearest) / SUPPLY_RADIUS_M).clip(0, 1)
    df["supply"] = df["stations_2km"] + df["near"]
    df["discount"] = 1.0 / (1.0 + df["supply"])
    df["contested"] = df["U"] * df["discount"]

    print("\n--- what each term actually varies by ---")
    print(f"{'term':<26}{'p5':>10}{'p50':>10}{'p95':>10}{'p95/p5':>10}")
    for name in ("U", "discount", "contested"):
        s = df[name]
        print(f"  {name:<24}{s.quantile(0.05):>10.4f}{s.median():>10.4f}"
              f"{s.quantile(0.95):>10.4f}{spread(s):>10.2f}x")
    print(f"  {'stations_2km':<24}{df.stations_2km.quantile(0.05):>10.0f}"
          f"{df.stations_2km.median():>10.0f}{df.stations_2km.quantile(0.95):>10.0f}"
          f"{'':>10}  (max {df.stations_2km.max():.0f})")

    print("\n--- which term the ranking follows (Spearman, on unbuilt cells) ---")
    unbuilt = df[df.station_count == 0]
    print(f"  unbuilt cells         : {len(unbuilt):,}")
    for label, series in (("supply discount alone", unbuilt["discount"]),
                          ("the ML prediction alone", unbuilt["U"])):
        r = unbuilt["contested"].corr(series, method="spearman")
        print(f"  contested vs {label:<24}: {r:+.4f}")

    print("\n--- damping: 1/(1+supply)^alpha ---")
    print("  alpha  discount spread   contested spread   rho(contested, discount)   rho(contested, U)")
    for alpha in (1.0, 0.75, 0.5, 0.35, 0.25):
        d = 1.0 / np.power(1.0 + unbuilt["supply"], alpha)
        contested = unbuilt["U"] * d
        print(f"  {alpha:<5.2f}  {spread(d):>14.2f}x  {spread(contested):>16.2f}x"
              f"  {contested.corr(d, method='spearman'):>24.4f}"
              f"  {contested.corr(unbuilt['U'], method='spearman'):>18.4f}")

    # The chosen shape: explicit weights over percentile ranks, mirroring
    # services/site_scoring.py. Multiplication was measured above and rejected --
    # it turned out 84% supply, because demand and supply are already negatively
    # correlated in Jabodetabek and the two terms cancel.
    print("\n--- rank blend: w*rank(U) + (1-w)*rank(discount) ---")
    ru = unbuilt["U"].rank(pct=True)
    rd = unbuilt["discount"].rank(pct=True)
    print(f"  rank(U) vs rank(discount) correlate at "
          f"{ru.corr(rd, method='spearman'):+.4f}  <- why multiplying cancelled them")
    print(f"\n  {'w':>5}{'rho(suit,U)':>14}{'rho(suit,disc)':>16}"
          f"{'served->green':>15}{'red with 0 nearby':>20}")
    for w in (0.7, 0.6, 0.5, 0.4, 0.3, 0.2):
        suit = w * ru + (1 - w) * rd
        red, mid = suit.quantile(0.90), suit.quantile(0.50)
        served = unbuilt["stations_2km"] >= 1
        green_when_served = 100 * (suit[served] < mid).mean()
        red_cells = suit >= red
        clean_red = 100 * (unbuilt.loc[red_cells, "stations_2km"] == 0).mean()
        print(f"  {w:>5.1f}{suit.corr(ru, method='spearman'):>14.4f}"
              f"{suit.corr(rd, method='spearman'):>16.4f}"
              f"{green_when_served:>14.0f}%{clean_red:>19.0f}%")
    print("\n  served->green: share of cells with a station within 2 km that fall below the")
    print("  regional median, which is AC (c). red with 0 nearby: share of the top decile")
    print("  that has no competitor at all, which is what a shortlist should look like.")

    print("\n--- does an over-saturated cell actually land low? (AC (c)) ---")
    q = unbuilt["contested"].quantile
    for n in (0, 1, 3, 5):
        sub = unbuilt[unbuilt.stations_2km == n]
        if sub.empty:
            continue
        below_median = 100 * (sub["contested"] < q(0.50)).mean()
        print(f"  stations_2km = {n}: {len(sub):>6,} cells, median contested "
              f"{sub['contested'].median():.3f}, {below_median:.0f}% below the regional median")
    return 0


if __name__ == "__main__":
    sys.exit(main())
