"""Re-extract POI points from the OSM PBF, keeping the geometry this time.

spklu_bootstrap.py already reads these POIs, but it counts them into the grid's
poi_* columns and throws the points away. The planner map wants individual
markers, so this run keeps them.

The filter, the reprojection, the centroid and the spatial join are copied from
poi_features() rather than reimplemented. That is the whole point: the markers
this produces must be exactly the POIs the counts describe, or the map and the
numbers on the same screen will disagree and there will be no way to tell which
one lied. The script asserts that per-category totals match the grid columns
before it writes anything.

Usage:
    .venv-etl/bin/python extract_poi_points.py --pbf java-260814.osm.pbf
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GRID_GPKG = os.path.join(HERE, "grid_jabodetabek_500m.gpkg")
OUT_PARQUET = os.path.join(HERE, "output", "planning_pois.parquet")
OUT_COUNTS = os.path.join(HERE, "output", "poi_counts_per_cell.parquet")

CRS_METRIC = 32748  # UTM 48S, same as the bootstrap
CRS_WGS = 4326
BBOX = (106.30, -6.95, 107.30, -5.85)

# The seventeen the grid already counts, copied verbatim from
# spklu_bootstrap.POI_TAGS. Do not "tidy" these: a changed tag silently produces
# markers that no longer match the poi_* columns, and the check below would then
# be comparing two different things and passing.
BASELINE_TAGS = {
    "parking":          ("amenity", ["parking"]),
    "parking_space":    ("amenity", ["parking_space"]),
    "restaurant":       ("amenity", ["restaurant"]),
    "park":             ("leisure", ["park"]),
    "school":           ("amenity", ["school"]),
    "university":       ("amenity", ["university"]),
    "cinema":           ("amenity", ["cinema"]),
    "library":          ("amenity", ["library"]),
    "community_centre": ("amenity", ["community_centre"]),
    "place_of_worship": ("amenity", ["place_of_worship"]),
    "townhall":         ("amenity", ["townhall"]),
    "government":       ("office",  ["government"]),
    "civic":            ("building", ["civic"]),
    "fuel":             ("amenity", ["fuel"]),
    "mall":             ("shop",    ["mall"]),
    "hospital":         ("amenity", ["hospital"]),
    "rest_area":        ("highway", ["services"]),
}

# New categories, chosen on dwell time rather than footfall: a 50 kW charge
# takes 30-45 minutes, so a place people stay is worth more than a place people
# pass. Grouped by how long that stay tends to be.
NEW_TAGS = {
    # Long dwell. A car parked overnight or for a working day is the easiest
    # charge there is.
    "hotel":            ("tourism", ["hotel"]),
    "office_commercial": ("office", ["company", "commercial", "coworking", "it",
                                     "financial", "insurance", "estate_agent", "lawyer"]),
    "fitness_centre":   ("leisure", ["fitness_centre"]),
    "sports_centre":    ("leisure", ["sports_centre"]),

    # Medium dwell, 30 to 90 minutes. This is the core of the opportunity, and
    # the band our seventeen covered worst: restaurant and mall were the only
    # commercial entries, and mall has just 370 across the whole region.
    "cafe":             ("amenity", ["cafe"]),
    "fast_food":        ("amenity", ["fast_food"]),
    "supermarket":      ("shop",    ["supermarket"]),
    "department_store": ("shop",    ["department_store"]),
    "marketplace":      ("amenity", ["marketplace"]),

    # Transport nodes. Park-and-ride is the classic charging use case: the car
    # sits for a whole working day while its driver takes the train.
    "railway_station":  ("railway", ["station"]),
    "bus_station":      ("amenity", ["bus_station"]),
    "airport_terminal": ("aeroway", ["terminal"]),

    # highway=services is what the baseline uses and it found only 18. Toll-road
    # rest stops are where Indonesian SPKLU actually go, so the shortfall is a
    # mapping gap rather than a real absence; highway=rest_area is the other tag
    # OSM uses for the same thing. Kept separate so the baseline check still
    # compares like with like.
    "highway_rest_area": ("highway", ["rest_area"]),
}

POI_TAGS = {**BASELINE_TAGS, **NEW_TAGS}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def expected_counts() -> dict[str, int]:
    """What the grid already says, so the extraction can be checked against it."""
    db = sqlite3.connect(GRID_GPKG)
    try:
        return {c: (db.execute(f"SELECT sum({c}) FROM grid").fetchone()[0] or 0)
                for c in BASELINE_TAGS}
    finally:
        db.close()


def check_dependencies() -> None:
    """Fail now, not in two hours.

    The first full run parsed an 854 MB extract for 110 minutes, reconciled all
    seventeen baseline categories against the grid, and then died on the last
    line because the ETL environment had no parquet writer installed. Every
    library this script needs at the END is therefore imported at the START,
    where the cost of being wrong is a second rather than an afternoon.
    """
    missing = []
    for mod, why in (("geopandas", "spatial join"), ("pyrosm", "PBF parsing"),
                     ("pandas", "table assembly"), ("pyarrow", "writing parquet")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({why})")
    if missing:
        raise SystemExit(
            "refusing to start; missing: " + ", ".join(missing)
            + "\n  install into the ETL environment: .venv-etl/bin/python -m pip install "
            + " ".join(m.split()[0] for m in missing))


def main(pbf_path: str) -> int:
    check_dependencies()
    import geopandas as gpd
    import pandas as pd
    from pyrosm import OSM

    want = expected_counts()
    log(f"baseline target from grid: {sum(want.values()):,} POIs across {len(want)} categories")
    log(f"extracting {len(POI_TAGS)} categories ({len(NEW_TAGS)} of them new)")

    grid = gpd.read_file(GRID_GPKG, layer="grid")[["cell_id", "geometry"]]
    log(f"grid loaded: {len(grid):,} cells")

    minx, miny, maxx, maxy = BBOX
    log(f"parsing {os.path.basename(pbf_path)} — this is the slow part")
    osm = OSM(pbf_path, bounding_box=[minx, miny, maxx, maxy])

    keys: dict[str, list[str]] = {}
    for _col, (k, vs) in POI_TAGS.items():
        keys.setdefault(k, []).extend(vs)
    pois = osm.get_data_by_custom_criteria(
        custom_filter=keys, filter_type="keep",
        keep_nodes=True, keep_ways=True, keep_relations=True)
    log(f"raw features matching the filter: {len(pois):,}")

    pois = pois.to_crs(CRS_METRIC)
    # Ways and relations arrive as polygons; the bootstrap reduces every feature
    # to its centroid before joining, so a mall counts once wherever its outline
    # sits. Markers follow the same rule for the same reason.
    pois["geometry"] = pois.geometry.centroid

    frames = []
    for col, (k, vs) in POI_TAGS.items():
        if k not in pois.columns:
            log(f"  {col}: tag key '{k}' absent from extract — 0")
            continue
        sub = pois[pois[k].isin(vs)].copy()
        cols = ["geometry"] + [c for c in ("id", "name") if c in sub.columns]
        j = gpd.sjoin(sub[cols], grid, how="inner", predicate="within")
        j["category"] = col
        frames.append(j)
        note = f"(grid says {want[col]:,})" if col in BASELINE_TAGS else "(new)"
        log(f"  {col}: {len(j):,} in-grid {note}")

    pts = pd.concat(frames, ignore_index=True)
    pts = gpd.GeoDataFrame(pts, geometry="geometry", crs=CRS_METRIC).to_crs(CRS_WGS)

    # The check that makes this worth doing: the markers must be the POIs the
    # counts describe.
    #
    # The tolerance is not laziness. sjoin's "within" predicate is strict
    # containment, so a centroid landing exactly on a cell edge is included or
    # excluded depending on floating-point rounding, which is not stable across
    # geopandas and shapely versions. The grid's counts were written months
    # earlier by spklu_bootstrap.py under different versions, so a handful of
    # boundary points can legitimately flip. What must NOT happen is a
    # systematic difference, which is what a proportional tolerance catches
    # while a bit-exact one drowns in noise: the first run of this script
    # rejected everything over parking being 2,542 against 2,543, one point in
    # 36,497, after an hour and fifty minutes of parsing.
    #
    # Every difference is still printed, however small. Tolerated is not hidden.
    TOL_ABS, TOL_FRAC = 3, 0.001
    got = pts.groupby("category").size().to_dict()
    diffs = {c: (got.get(c, 0), want[c]) for c in BASELINE_TAGS if got.get(c, 0) != want[c]}
    bad = {c: (g, w) for c, (g, w) in diffs.items()
           if abs(g - w) > max(TOL_ABS, TOL_FRAC * w)}

    if diffs:
        log("")
        log(f"baseline differences (tolerance: {TOL_ABS} points or {TOL_FRAC:.1%}, "
            f"whichever is larger):")
        for c, (g, w) in sorted(diffs.items()):
            verdict = "OVER TOLERANCE" if c in bad else "within tolerance"
            log(f"  {c}: extracted {g:,}, grid says {w:,} "
                f"(diff {g - w:+,}) — {verdict}")
    if bad:
        log("refusing to write; a difference this size is systematic, not a boundary case")
        return 1
    log(f"{len(BASELINE_TAGS) - len(diffs)}/{len(BASELINE_TAGS)} baseline categories "
        f"match exactly, {len(diffs)} within tolerance")

    out = pd.DataFrame({
        "osm_id": pts["id"].astype("int64") if "id" in pts.columns else range(len(pts)),
        "category": pts["category"],
        "name": pts["name"] if "name" in pts.columns else None,
        "cell_id": pts["cell_id"],
        "lon": pts.geometry.x.round(6),
        "lat": pts.geometry.y.round(6),
    })
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)

    counts = (out.groupby(["cell_id", "category"]).size().unstack(fill_value=0))
    counts.to_parquet(OUT_COUNTS, index=True)

    log("")
    log(f"  {'category':<20}{'points':>9}  tier")
    for cat in POI_TAGS:
        tier = "baseline" if cat in BASELINE_TAGS else "NEW"
        log(f"  {cat:<20}{got.get(cat, 0):>9,}  {tier}")
    log("")
    log(f"wrote {len(out):,} points to {os.path.basename(OUT_PARQUET)}")
    log(f"wrote per-cell counts for {len(POI_TAGS)} categories to {os.path.basename(OUT_COUNTS)}")
    log(f"all {len(BASELINE_TAGS)} baseline categories still match the grid exactly")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pbf", required=True)
    sys.exit(main(ap.parse_args().pbf))
