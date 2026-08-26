"""Store the land-use polygons themselves, not only their per-cell share.

WHAT WAS MISSING

planning_cells carries lu_commercial_share and its three siblings: how much of a
500 m cell each class covers. Useful as model features, useless as a map. The
Land Use layer had nothing else to draw with, so it painted squares tinted by
four blended proportions -- a city block and the road beside it came out the same
colour, and the shapes that produced the numbers were computed, measured, and
discarded.

This table keeps them. Same geometries the shares are measured from, written by
the same pass (ev-planner-study/recompute_landuse.py), so the map and the
features cannot drift apart.

WHY CLASSES DO NOT OVERLAP HERE EITHER

The polygons are the priority-resolved ones: every square metre belongs to
exactly one class, the most specific that claims it (retail > commercial >
industrial > residential). OSM nests these -- a retail park inside a residential
district -- and unresolved they would both double-count in the shares and paint
over each other on the map, with the drawing order deciding what a planner sees.

The share fix and the map fix are therefore the same fix, which is why one table
and one script produce both.

SRID 4326, not the metric 32748 the pipeline computes in: this is served to a
web map, and PostGIS transforms once at load rather than per request.

Revision ID: 0026_planning_landuse
Revises: 0025_occupancy_full_window
"""
from alembic import op

revision = "0026_planning_landuse"
down_revision = "0025_occupancy_full_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_landuse (
            id       BIGSERIAL PRIMARY KEY,
            -- One of the resolved classes. Text rather than an enum: OSM adds
            -- land-use values faster than a migration can follow, and widening
            -- the map's palette should not need a schema change.
            landuse  TEXT NOT NULL,
            geom     geometry(Polygon, 4326) NOT NULL,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # The layer is always read by viewport, never whole, so the bbox index is
    # the only one that matters. Without it a pan reads every polygon in
    # Jabodetabek and discards most of them.
    op.execute("CREATE INDEX IF NOT EXISTS planning_landuse_geom_ix "
               "ON planning_landuse USING GIST (geom)")
    op.execute("CREATE INDEX IF NOT EXISTS planning_landuse_class_ix "
               "ON planning_landuse (landuse)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS planning_landuse")
