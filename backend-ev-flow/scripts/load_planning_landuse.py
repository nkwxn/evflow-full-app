"""Load the resolved land-use polygons into planning_landuse.

    python -m scripts.load_planning_landuse --gpkg ../ev-planner-study/landuse_jabodetabek.gpkg

The `landuse` layer of landuse_jabodetabek.gpkg, which
ev-planner-study/recompute_landuse.py writes in the same pass as the per-cell
shares in the grid file. One pass, two outputs measured from one set of
geometries, so the map a planner reads and the features a model reads cannot
describe different land.

WHY A FULL REPLACE AND NOT AN UPSERT

The polygons have no stable identity. They are the union of every OSM way of a
class, cut against the classes above it in priority, then exploded -- add one
building to OSM and the shape that contains it merges, splits or moves, so a row
id from the last run means nothing this run. Deleting and reinserting inside one
transaction is both correct and, at this size, faster than matching would be.

No geopandas, fiona or pyproj, for the same reason as load_planning_cells: a
GeoPackage is SQLite and its geometry column is a short header followed by
ordinary WKB, so the blob goes straight to PostGIS. The heavy geospatial stack
stays out of the API image.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import text

from api.db import engine
from scripts.load_planning_cells import _gpkg_wkb

#: recompute_landuse.py writes this layer in 4326 already, so nothing is
#: transformed here. Asserting it rather than assuming: a layer written in the
#: pipeline's metric CRS would load without error and put Jabodetabek in the
#: Atlantic.
LAYER_SRID = 4326


def load(gpkg_path: Path, batch: int = 1000) -> int:
    con = sqlite3.connect(gpkg_path)
    try:
        layers = {r[0] for r in con.execute(
            "SELECT table_name FROM gpkg_contents").fetchall()}
        if "landuse" not in layers:
            raise SystemExit(
                f"{gpkg_path} has no 'landuse' layer (found: {', '.join(sorted(layers))}). "
                f"Run ev-planner-study/recompute_landuse.py first.")
        srid = con.execute(
            "SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = 'landuse'").fetchone()[0]
        if srid != LAYER_SRID:
            raise SystemExit(f"landuse layer is SRID {srid}, expected {LAYER_SRID}")
        rows = con.execute("SELECT landuse, geom FROM landuse").fetchall()
    finally:
        con.close()

    insert = text(f"""
        INSERT INTO planning_landuse (landuse, geom)
        VALUES (:landuse, ST_GeomFromWKB(:wkb, {LAYER_SRID}))
    """)

    with engine.begin() as c:
        c.execute(text("DELETE FROM planning_landuse"))
        payload = []
        for landuse, blob in rows:
            payload.append({"landuse": landuse, "wkb": _gpkg_wkb(blob)})
            if len(payload) >= batch:
                c.execute(insert, payload)
                payload = []
        if payload:
            c.execute(insert, payload)
        total = c.execute(text("SELECT count(*) FROM planning_landuse")).scalar()
        by_class = c.execute(text(
            "SELECT landuse, count(*) FROM planning_landuse GROUP BY 1 ORDER BY 2 DESC"
        )).all()

    for name, n in by_class:
        print(f"  {name:<14} {n:>8,}")
    print(f"  {'total':<14} {total:>8,}")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gpkg", required=True, type=Path,
                    help="landuse_jabodetabek.gpkg from recompute_landuse.py")
    args = ap.parse_args()
    if not args.gpkg.exists():
        print(f"no such file: {args.gpkg}", file=sys.stderr)
        return 2
    load(args.gpkg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
