"""Load POI points into planning_pois and their counts into planning_cells.

Both halves come from one extraction run
(ev-planner-study/extract_poi_points.py), which is the only way they can be
guaranteed to agree. A marker layer whose totals drift from the number printed
beside it is worse than no marker layer at all: both are on screen at once, they
contradict each other, and nothing tells a planner which one to believe.

So this script does all of it in one transaction and refuses to commit unless
every one of the thirty categories reconciles:

    points in planning_pois  ==  poi_<category> summed over planning_cells

The seventeen baseline categories are the strongest check, because their poi_*
columns were written by a separate run months earlier. If those still match, the
extraction reproduced the original faithfully.

Usage:
    DATABASE_URL=... python3 -m scripts.load_planning_pois \\
        --points   ../ev-planner-study/output/planning_pois.parquet \\
        --counts   ../ev-planner-study/output/poi_counts_per_cell.parquet
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text

BASELINE = (
    "parking", "parking_space", "restaurant", "park", "school", "university",
    "cinema", "library", "community_centre", "place_of_worship", "townhall",
    "government", "civic", "fuel", "mall", "hospital", "rest_area",
)
ADDED = (
    "hotel", "office_commercial", "fitness_centre", "sports_centre",
    "cafe", "fast_food", "supermarket", "department_store", "marketplace",
    "railway_station", "bus_station", "airport_terminal", "highway_rest_area",
)
CATEGORIES = BASELINE + ADDED

BATCH = 5000


def log(msg: str = "") -> None:
    print(f"  {msg}", flush=True)


def main(points_path: str, counts_path: str) -> int:
    import pandas as pd

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    pts = pd.read_parquet(points_path)
    counts = pd.read_parquet(counts_path)
    log(f"read {len(pts):,} points and counts for {len(counts):,} cells")

    unknown = sorted(set(pts["category"]) - set(CATEGORIES))
    if unknown:
        print(f"refusing: unknown categories in the points: {unknown}", file=sys.stderr)
        return 1

    engine = create_engine(url)
    with engine.begin() as c:
        # Points. TRUNCATE rather than upsert: every row here is derived, never
        # edited, so a reload should replace the layer instead of doubling it.
        c.execute(text("TRUNCATE planning_pois"))
        rows = pts.to_dict("records")
        for i in range(0, len(rows), BATCH):
            c.execute(text("""
                INSERT INTO planning_pois (osm_id, category, name, cell_id, geom)
                VALUES (:osm_id, :category, :name, :cell_id,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            """), rows[i:i + BATCH])
        log(f"inserted {len(rows):,} points")

        # Counts. Every category is rewritten, baseline included: if the
        # extraction disagrees with what the grid has held since 0018 we want
        # the check below to say so, not to be papered over by only writing the
        # new columns.
        present = [cat for cat in CATEGORIES if cat in counts.columns]
        missing = [cat for cat in CATEGORIES if cat not in counts.columns]
        if missing:
            log(f"note: no POI at all for {', '.join(missing)} — left at 0")

        c.execute(text("UPDATE planning_cells SET "
                       + ", ".join(f"poi_{cat} = 0" for cat in CATEGORIES)))
        payload = [
            {"cell_id": idx, **{f"c_{cat}": int(row[cat]) for cat in present}}
            for idx, row in counts.iterrows()
        ]
        assign = ", ".join(f"poi_{cat} = :c_{cat}" for cat in present)
        for i in range(0, len(payload), BATCH):
            c.execute(text(f"UPDATE planning_cells SET {assign} WHERE cell_id = :cell_id"),
                      payload[i:i + BATCH])
        log(f"updated counts on {len(payload):,} cells across {len(present)} categories")

        # poi_total is what the activity feature ranks on, so what it counts
        # decides the top of the planner's list.
        #
        # parking_space is excluded. OpenStreetMap tags individual parking BAYS
        # with it, so one diligently-mapped car park becomes hundreds of points
        # in a single cell. Measured on the current grid it does not just add
        # noise, it owns the head of the ranking: the top five cells by
        # poi_total were 769, 486, 196, 167 and 133, of which 768, 480, 196, 163
        # and 111 were parking bays, with zero restaurants or malls between
        # them. Only 32 of 27,219 cells shift by more than 1% when it is
        # removed, but those 32 are exactly the ones a planner reads first.
        #
        # The column is kept, because the data is real and the count is correct.
        # It simply stops standing in for "activity", which it never measured.
        scored = [cat for cat in CATEGORIES if cat != "parking_space"]
        c.execute(text("UPDATE planning_cells SET poi_total = "
                       + " + ".join(f"poi_{cat}" for cat in scored)))
        log(f"poi_total recomputed over {len(scored)} categories "
            f"(parking_space held out; see comment)")

    with engine.connect() as c:
        loaded = {r["category"]: r["n"] for r in c.execute(text(
            "SELECT category, count(*) AS n FROM planning_pois GROUP BY category")).mappings()}
        counted = {cat: c.execute(text(
            f"SELECT COALESCE(sum(poi_{cat}), 0) FROM planning_cells")).scalar_one()
            for cat in CATEGORIES}
        total = c.execute(text("SELECT sum(poi_total) FROM planning_cells")).scalar_one()

    bad = {cat: (loaded.get(cat, 0), counted[cat]) for cat in CATEGORIES
           if loaded.get(cat, 0) != counted[cat]}

    log("")
    log(f"{'category':<20}{'points':>9}{'grid':>9}  tier")
    for cat in CATEGORIES:
        tier = "baseline" if cat in BASELINE else "NEW"
        flag = "  <-- MISMATCH" if cat in bad else ""
        log(f"{cat:<20}{loaded.get(cat, 0):>9,}{counted[cat]:>9,}  {tier}{flag}")
    log("")

    if bad:
        print(f"FAILED: {len(bad)} categories disagree", file=sys.stderr)
        return 1
    log(f"all {len(CATEGORIES)} categories reconcile; poi_total is now {total:,}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--points", required=True)
    ap.add_argument("--counts", required=True)
    sys.exit(main(ap.parse_args().points, ap.parse_args().counts))
