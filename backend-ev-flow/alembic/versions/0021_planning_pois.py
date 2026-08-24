"""planning_pois: the individual POI points behind the grid's poi_* counts.

planning_cells already carries seventeen poi_* columns, one count per category.
Counts are what the score needs; they are not what a map needs. A planner asking
"why does this cell score well on activity" wants to see the restaurants, not
read the number six.

These are the same POIs. The extraction reuses spklu_bootstrap's tag filter,
reprojection and centroid rule verbatim, and refuses to write unless every
per-category total equals the matching poi_* column. So a marker layer and the
number printed next to it can never describe different things.

The category CHECK is deliberate. 0018 shipped land-use shares above 1.0 because
nothing rejected them on the way in, and the values were only noticed when they
were read back out. A category outside the seventeen is the same class of
mistake: harmless-looking on insert, and invisible until a layer silently
returns nothing.

downgrade() refuses, for the reason 0018 refuses: rebuilding this table means
re-parsing an 854 MB OSM extract offline, so dropping it to undo a schema change
discards work that takes far longer to redo than the change took to make.

Revision ID: 0021_planning_pois
Revises: 0020_planner_saved_sites
"""
from alembic import op

revision = "0021_planning_pois"
down_revision = "0020_planner_saved_sites"
branch_labels = None
depends_on = None


CATEGORIES = (
    "parking", "parking_space", "restaurant", "park", "school", "university",
    "cinema", "library", "community_centre", "place_of_worship", "townhall",
    "government", "civic", "fuel", "mall", "hospital", "rest_area",
)


def upgrade() -> None:
    allowed = ", ".join(f"'{c}'" for c in CATEGORIES)
    op.execute(f"""
        CREATE TABLE planning_pois (
            id       bigserial PRIMARY KEY,
            -- OSM id of the node/way/relation. Not unique: a way and a relation
            -- can share an id in OSM's numbering, and the same feature can be
            -- tagged into two categories.
            osm_id   bigint,
            category text NOT NULL CHECK (category IN ({allowed})),
            name     text,
            -- The cell this POI was counted into, from the same spatial join
            -- that produced the poi_* columns. Lets a cell's detail panel list
            -- its own POIs without a second spatial query.
            cell_id  text NOT NULL REFERENCES planning_cells(cell_id) ON DELETE CASCADE,
            geom     geometry(Point, 4326) NOT NULL
        )
    """)
    # The map always queries by viewport, so the spatial index is the one that
    # matters; category is a cheap secondary filter on top of it.
    op.execute("CREATE INDEX planning_pois_geom_gix ON planning_pois USING GIST (geom)")
    op.execute("CREATE INDEX planning_pois_category_ix ON planning_pois (category)")
    op.execute("CREATE INDEX planning_pois_cell_ix ON planning_pois (cell_id)")


def downgrade() -> None:
    raise NotImplementedError(
        "Refusing to drop planning_pois. Rebuilding it means re-parsing an 854 MB "
        "OSM extract offline, so an automatic downgrade would discard an hour of "
        "work to undo a schema change. Drop it by hand if that is genuinely what "
        "you want."
    )
