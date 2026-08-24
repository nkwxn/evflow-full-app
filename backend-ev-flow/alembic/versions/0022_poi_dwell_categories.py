"""Thirteen more POI categories, chosen for dwell time.

The original seventeen were ported from a German study's schema. Measured on our
own grid they turned out badly weighted for charging: school (9,942) and
place_of_worship (9,921) alone are 54% of all POIs, and both mark "people live
nearby" rather than "cars stop here". On the commercial side there were only
restaurant (4,129) and mall (370) across the whole region.

A 50 kW charge takes 30 to 45 minutes, so what matters is how long a car stays,
not how many people pass. The additions fill that in:

  long dwell    hotel, office_commercial, fitness_centre, sports_centre
  medium dwell  cafe, fast_food, supermarket, department_store, marketplace
  transport     railway_station, bus_station, airport_terminal
  mapping gap   highway_rest_area

highway_rest_area is separate from the existing rest_area rather than merged
into it. rest_area reads highway=services and found only 18 in all of
Jabodetabek, which is a tagging shortfall rather than a real absence: toll-road
rest stops are exactly where Indonesian SPKLU get built. Keeping them apart
means the extraction can still check its seventeen baseline categories against
the counts they have always had.

poi_total is recomputed here rather than left alone. It is the column the
activity feature ranks on, so leaving it describing seventeen categories while
thirty exist would make every score quietly wrong in a way nothing would flag.

Scores WILL move after this migration. That is intended: the activity percentile
is computed over a different, better-balanced set of features. The candidate
list changes with it, and the model needs retraining
(ev-planner-study/train_siting_model.py).

Revision ID: 0022_poi_dwell_categories
Revises: 0021_planning_pois
"""
from alembic import op

revision = "0022_poi_dwell_categories"
down_revision = "0021_planning_pois"
branch_labels = None
depends_on = None


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
ALL_CATEGORIES = BASELINE + ADDED


def upgrade() -> None:
    # New count columns, one per added category, matching the existing poi_*
    # shape. NOT NULL DEFAULT 0 so the table stays queryable between this
    # migration and the reload that fills them.
    cols = ",\n            ".join(
        f"ADD COLUMN IF NOT EXISTS poi_{c} integer NOT NULL DEFAULT 0 CHECK (poi_{c} >= 0)"
        for c in ADDED)
    op.execute(f"ALTER TABLE planning_cells\n            {cols}")

    # planning_pois.category is constrained to the seventeen by 0021. Widen it,
    # rather than dropping the constraint: an unconstrained category column is
    # how a typo becomes a layer that silently returns nothing.
    allowed = ", ".join(f"'{c}'" for c in ALL_CATEGORIES)
    op.execute("ALTER TABLE planning_pois DROP CONSTRAINT IF EXISTS planning_pois_category_check")
    op.execute(f"ALTER TABLE planning_pois ADD CONSTRAINT planning_pois_category_check "
               f"CHECK (category IN ({allowed}))")

    # poi_total must describe every category it now has, or the activity feature
    # ranks on a number that stopped matching its own columns.
    #
    # Except parking_space, which is held out. OSM tags individual parking BAYS
    # with it, so one well-mapped car park becomes hundreds of points in one
    # cell: the top five cells by poi_total were 769, 486, 196, 167 and 133,
    # and 768, 480, 196, 163 and 111 of those were bays, with no restaurants or
    # malls among them. Only 32 of 27,219 cells move by more than 1% without it,
    # but those 32 are the head of the list a planner actually reads. The column
    # stays; it just stops standing in for activity, which it never measured.
    scored = [c for c in ALL_CATEGORIES if c != "parking_space"]
    total = " + ".join(f"poi_{c}" for c in scored)
    op.execute(f"UPDATE planning_cells SET poi_total = {total}")


def downgrade() -> None:
    total = " + ".join(f"poi_{c}" for c in BASELINE)
    op.execute(f"UPDATE planning_cells SET poi_total = {total}")
    allowed = ", ".join(f"'{c}'" for c in BASELINE)
    op.execute("DELETE FROM planning_pois WHERE category NOT IN (%s)" % allowed)
    op.execute("ALTER TABLE planning_pois DROP CONSTRAINT IF EXISTS planning_pois_category_check")
    op.execute(f"ALTER TABLE planning_pois ADD CONSTRAINT planning_pois_category_check "
               f"CHECK (category IN ({allowed}))")
    cols = ", ".join(f"DROP COLUMN IF EXISTS poi_{c}" for c in ADDED)
    op.execute(f"ALTER TABLE planning_cells {cols}")
