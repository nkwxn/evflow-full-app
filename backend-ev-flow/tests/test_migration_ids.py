"""Revision ids must fit the column alembic stores them in.

WHY THIS TEST EXISTS

alembic_version.version_num is varchar(32). Alembic updates that row inside the
SAME transaction as the migration body, so an id one character too long does not
fail before the work -- it fails after, and Postgres rolls the migration back
while the log line "Running upgrade X -> Y" is already on the screen. The
operator is left with a migration that announced itself, changed nothing, and
raised a StringDataRightTruncation about a column they never wrote to.

That happened on 2026-08-24 with a 38-character id, against a live database, one
command before a procedure was about to be replaced. The margin was already thin:
0024_demand_factor_station_rank is 31 characters.

No database is needed to catch it, which is the point -- this must fail in the
suite, not at the moment of applying.
"""
import re
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: alembic's own default for the version table. Raising it means an ALTER on
#: every deployed database, so treat it as fixed and keep ids short instead.
MAX_ID = 32

_ASSIGN = re.compile(r'^(revision|down_revision)\s*=\s*["\']([^"\']+)["\']', re.M)


def _ids():
    for path in sorted(VERSIONS.glob("*.py")):
        for kind, value in _ASSIGN.findall(path.read_text()):
            yield path.name, kind, value


def test_there_are_migrations_to_check():
    # A glob that quietly matches nothing would make every assertion below pass.
    assert list(_ids()), f"no revision ids found under {VERSIONS}"


@pytest.mark.parametrize("name,kind,value", list(_ids()))
def test_every_revision_id_fits_the_version_column(name, kind, value):
    assert len(value) <= MAX_ID, (
        f"{name}: {kind} '{value}' is {len(value)} characters, over the {MAX_ID} "
        f"that alembic_version.version_num holds. The migration will run and then "
        f"roll back when alembic stamps the version.")


def test_no_two_migrations_claim_the_same_revision():
    seen = {}
    for name, kind, value in _ids():
        if kind != "revision":
            continue
        assert value not in seen, f"{name} and {seen[value]} both claim '{value}'"
        seen[value] = name


def test_every_down_revision_points_at_a_real_migration():
    revisions = {v for _, k, v in _ids() if k == "revision"}
    for name, kind, value in _ids():
        if kind == "down_revision":
            assert value in revisions, f"{name}: down_revision '{value}' does not exist"
