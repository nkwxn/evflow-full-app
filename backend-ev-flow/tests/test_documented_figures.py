"""The figures quoted to users must still be true.

Three numbers in this codebase drifted without anything noticing, and two of
them reached the screen through the interpretation string the planner card
prints:

    stations the model learned from   1,236 -> 1,192
    of those, operated by PLN         1,080 -> 1,038
    grid cell size                    "400 m" -> 500 m

Each was correct when written and had no way to stay correct. That is the same
failure EMPTY_CELL_CEILING = 0.31 made before resemblance_scale replaced it with
a derivation -- and the comment on PlannerAreaDistribution says so, two hundred
lines above three constants repeating it.

Where a figure can be derived it should be, and the model's own counts already
are: /planner/model reads n_samples and n_positive out of the artifact. The
station counts cannot be derived without a spatial join per request, so they stay
written down -- and these tests recompute them, so the next drift fails here
instead of being read off a card by a planner.
"""
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import requires_db

API = Path(__file__).resolve().parents[1] / "api"

#: The join the quoted share comes from: stations inside the cells the planner
#: actually scores, which is a smaller population than the stations table.
SCORED_STATIONS_SQL = """
    SELECT count(DISTINCT s.id) FILTER (WHERE s.operator = 'PLN') AS pln,
           count(DISTINCT s.id)                                   AS total
      FROM stations s
      JOIN planning_cells pc ON ST_Within(s.geom, pc.geom)
     WHERE pc.overlap_frac >= 0.5 AND pc.kota <> 'Kepulauan Seribu'
"""


def _sources() -> str:
    """Every user-facing string and docstring in the API, as one blob."""
    return "\n".join(p.read_text() for p in sorted(API.rglob("*.py")))


@requires_db
def test_the_pln_share_quoted_to_users_is_still_the_measured_one():
    import os

    from sqlalchemy import create_engine

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as c:
        row = c.execute(text(SCORED_STATIONS_SQL)).mappings().one()

    blob = _sources()
    assert f"{row['total']:,}" in blob, (
        f"the code quotes a station count that is no longer {row['total']:,}")
    assert f"{row['pln']:,}" in blob, (
        f"the code quotes a PLN count that is no longer {row['pln']:,}")
    share = round(100 * row["pln"] / row["total"])
    assert f"{share}%" in blob, f"the quoted PLN share is no longer {share}%"


def test_no_source_claims_the_old_cell_size():
    # The grid is 500 m: GRID_SIZE in spklu_bootstrap, the filename, and
    # cell_size_m in the provenance all say so. Six places said 400.
    stale = [ln for ln in _sources().splitlines()
             if re.search(r"\b400 m (cells|resolution)\b", ln)]
    assert not stale, f"{len(stale)} line(s) still claim a 400 m grid: {stale[:2]}"


def test_no_source_repeats_the_unsupported_pln_rationale():
    """Why the network looks the way it does is not in any table here.

    "following PLN offices and policy targets" was an explanation of PLN's
    siting intent, printed to users beside numbers that sounded measured. There
    is no PLN-office column, no policy-target column, and nothing else in this
    repo that could support or refute it. The argument it decorated -- that a
    descriptive model is not a recommendation -- stands on its own evidence: the
    model's 500 highest cells are 100% already built.
    """
    assert "PLN offices and policy targets" not in _sources()


@requires_db
def test_the_grid_the_api_serves_is_the_size_the_docs_claim():
    import os

    from sqlalchemy import create_engine

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as c:
        side = c.execute(text("""
            SELECT round(sqrt(ST_Area(geom::geography))::numeric) FROM planning_cells
             WHERE overlap_frac >= 0.999 LIMIT 1
        """)).scalar()
    assert side is not None, "no full-overlap cell to measure"
    assert 480 <= float(side) <= 520, f"cells measure {side} m on a side, not 500"
