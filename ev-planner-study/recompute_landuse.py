"""Recompute land-use shares only, with the cross-class overlap resolved.

WHY THIS EXISTS SEPARATELY FROM spklu_bootstrap.py poi

That pass parses an 854 MB PBF for POIs, land use and the road network together,
and only the land-use third was wrong. Re-running all of it to fix one third
costs a long parse and risks disturbing two sets of features that are correct.

It imports landuse_shares from spklu_bootstrap rather than reimplementing it, so
the focused fix and the full pipeline cannot drift apart. Both produce numbers
between 0 and 1, so a drift between them would not look like a bug.

WHAT WAS WRONG

Shares are proportions of one cell's area and cannot sum above 1. Measured
2026-08-25 on the delivered grid, 657 of 27,219 cells summed over 1.0, because
OSM nests land-use classes -- a retail park inside a residential district -- and
each class counted the shared land as its own. Every square metre now goes to
exactly one class, the most specific that claims it.

WHAT THIS DOES NOT FIX

Half the grid has no land-use polygon of any class (13,791 of 27,219 cells), and
on the cells that do, about 22% of the area is classified. That is OSM's coverage
in Jabodetabek, not an error in this code, and no amount of geometry work here
changes it. Fixing it means a second source -- ESA WorldCover, Dynamic World, or
RTRW -- not a better intersection.

Usage:
    .venv-etl/bin/python recompute_landuse.py            # rewrite the gpkg
    .venv-etl/bin/python recompute_landuse.py --dry-run  # report, write nothing
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from spklu_bootstrap import (  # noqa: E402
    CRS_METRIC, GRID_GPKG, LANDUSE_SHARE, landuse_shares, log,
)

PBF = os.path.join(HERE, "java-260814.osm.pbf")

#: A separate file, not a second layer in the grid GeoPackage.
#:
#: Writing two layers to one GPKG in sequence risks the second write recreating
#: the dataset and taking the first layer with it, and a re-run with mode="a"
#: would instead append a duplicate copy of every polygon. Two files have
#: neither failure mode, and the consumers are different anyway:
#: load_planning_cells reads the grid, load_planning_landuse reads this.
LANDUSE_GPKG = os.path.join(HERE, "landuse_jabodetabek.gpkg")


def summarise(grid, label):
    total = sum(grid[f"lu_{c}_share"] for c in LANDUSE_SHARE)
    log(f"  {label}")
    for c in LANDUSE_SHARE:
        col = grid[f"lu_{c}_share"]
        log(f"    lu_{c:<12} cells>0 {int((col > 0).sum()):>6,}  mean {col.mean():.4f}  max {col.max():.2f}")
    log(f"    shares summing above 1.0 : {int((total > 1.0001).sum()):,}   <- must be 0")
    log(f"    cells with no land use   : {int((total == 0).sum()):,} of {len(grid):,}")
    log(f"    mean classified share    : {total.mean():.4f}")


def main() -> int:
    import geopandas as gpd
    import pandas as pd
    from pyrosm import OSM

    dry = "--dry-run" in sys.argv
    if not os.path.exists(PBF):
        log(f"missing {PBF}")
        return 2

    grid = gpd.read_file(GRID_GPKG, layer="grid").to_crs(CRS_METRIC)
    log(f"grid: {len(grid):,} cells")
    summarise(grid, "BEFORE (as delivered)")

    log("\n  reading land use from the PBF ...")
    lu = OSM(PBF).get_landuse().to_crs(CRS_METRIC)
    log(f"  landuse rows: {len(lu):,}")

    shares, geoms = landuse_shares(grid, lu, with_geometry=True)
    for cls in LANDUSE_SHARE:
        share = shares.get(cls)
        grid[f"lu_{cls}_share"] = (0.0 if share is None
                                   else grid["cell_id"].map(share).fillna(0.0).round(4))
    log("")
    summarise(grid, "AFTER (cross-class overlap resolved)")
    log("")
    log("  resolved polygons for the map layer")

    # The polygons themselves, for the map.
    #
    # Until now only the per-cell SHARES existed, so the Land Use layer could
    # only paint 500 m squares tinted by four blended proportions -- the shapes
    # were computed, measured, and thrown away. These are the same geometries the
    # shares above were measured from, so what a planner sees and what the model
    # reads cannot disagree.
    #
    # Exploded to single polygons and given the class as a column: one row per
    # shape is what a bbox query and a categorical legend both want.
    # Clipped to the study area, which the first version of this script forgot.
    #
    # The PBF is the whole Java extract, so the resolved geometry spans Banten to
    # Bali. Loaded unclipped it put 41,125 of 51,141 polygons -- 80.4% -- outside
    # the planning grid entirely: table bloat, a fatter index, and a map that
    # would happily paint land use over Surabaya where this tool has no cells, no
    # scores and no model.
    #
    # Polygons that STRADDLE the boundary are kept whole rather than cut. A
    # trimmed polygon would draw a straight edge that exists nowhere on the
    # ground, and the reader cannot tell that edge from a real one.
    study_area = grid.geometry.union_all().buffer(0)
    parts = []
    for cls, geom in geoms.items():
        if geom is None:
            continue
        piece = gpd.GeoDataFrame({"landuse": [cls]}, geometry=[geom], crs=grid.crs)
        piece = piece.explode(index_parts=False)
        piece = piece[piece.geometry.geom_type == "Polygon"]
        before = len(piece)
        piece = piece[piece.intersects(study_area)]
        # Slivers left by the difference operation: a few square metres of
        # numerical residue, invisible on any map and eight rows of noise.
        piece = piece[piece.area >= 1.0]
        piece = piece[piece.is_valid]
        parts.append(piece)
        log(f"    {cls:<12} {len(piece):>7,} polygons  (dropped {before - len(piece):,} "
            f"outside the study area, degenerate or invalid)")
    polygons = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=grid.crs)
    log(f"    {'total':<12} {len(polygons):>7,} polygons")

    if dry:
        log("\n  --dry-run: nothing written")
        return 0
    grid.to_file(GRID_GPKG, layer="grid", driver="GPKG")
    polygons.to_crs(4326).to_file(LANDUSE_GPKG, layer="landuse", driver="GPKG")
    log(f"\n  written {GRID_GPKG} (corrected shares)")
    log(f"  written {LANDUSE_GPKG} (polygons for the map layer)")
    log("  the database still holds the OLD values; load them separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
