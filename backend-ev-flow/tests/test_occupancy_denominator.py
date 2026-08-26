"""Occupancy is a mean over every occurrence of a slot, not over the busy ones.

THE BUG THIS PINS

Until 0025 the divisor was GREATEST(COUNT(DISTINCT occurred_on), 1): the number
of days on which that (station, day_of_week, hour) slot saw a session. A Monday
with no session did not pull the average down, it left the divisor. So a station
busy on one Monday at 09:00 and empty on the other three reported the occupancy
of that one Monday as its Monday-09:00 figure.

It can only read high, and api/stations_repo.get_hourly_occupancy turns the
figure into PEAK / BUSY / MODERATE / LOW at fixed thresholds, so the error
surfaces to a driver as a station described as busier than it is.

WHY THESE RUN AGAINST A REAL DATABASE

The bug is in an aggregate's divisor. A Python re-implementation would pin what
we believe the SQL says rather than what it does, and the belief was the thing
that was wrong. So the migration's own SQL is loaded from the migration file --
never copied here, where the two could drift -- and executed.

WHY NOTHING SHARED IS TOUCHED

The procedure is created as pg_temp.refresh_station_hourly_occupancy, explicitly
qualified, so it cannot overwrite the real one even for an instant. The tables it
reads are temporary tables of the same names, which shadow the real ones through
search_path. Everything dies with the session, and the real
station_hourly_occupancy is never written -- which matters because the only
database these run against is shared staging.
"""
import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.conftest import requires_db

MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
             / "0025_occupancy_full_window.py")

#: One connector, so capacity arithmetic is 60 minutes an hour and the expected
#: percentages can be read off by hand.
STATION = "TEST_OCC_DENOM"


def _procedure_sql(name: str) -> str:
    spec = importlib.util.spec_from_file_location("m0025", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sql = getattr(mod, name)
    # Qualified so it lands in the session's temp schema. Unqualified it would
    # replace the real procedure on whatever database the tests point at.
    assert "PROCEDURE refresh_station_hourly_occupancy()" in sql
    return sql.replace("PROCEDURE refresh_station_hourly_occupancy()",
                       "PROCEDURE pg_temp.refresh_station_hourly_occupancy()")


@pytest.fixture
def db():
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as c:
        c.execute(text("SET search_path TO pg_temp, public"))
        c.execute(text("""
            CREATE TEMP TABLE connectors (id SERIAL PRIMARY KEY, station_id TEXT NOT NULL)
        """))
        c.execute(text("""
            CREATE TEMP TABLE charging_sessions (
                id SERIAL PRIMARY KEY, station_id TEXT NOT NULL,
                created_at TIMESTAMPTZ, completed_at TIMESTAMPTZ)
        """))
        c.execute(text("""
            CREATE TEMP TABLE station_hourly_occupancy (
                station_id TEXT NOT NULL, day_of_week INT NOT NULL, hour_of_day INT NOT NULL,
                avg_occupancy NUMERIC, occupancy_level TEXT, last_updated TIMESTAMPTZ,
                UNIQUE (station_id, day_of_week, hour_of_day))
        """))
        c.execute(text("INSERT INTO connectors (station_id) VALUES (:s)"), {"s": STATION})
        yield c
        c.rollback()


def _sessions(c, weeks_back: list[int], minutes: int = 60) -> None:
    """One session per listed week, all in the same slot as this moment.

    Offsets are whole weeks, so every one lands on the same day_of_week and hour
    as now -- which is the point: they are repeat observations of ONE slot, and
    the divisor is what the test is about.
    """
    for w in weeks_back:
        c.execute(text("""
            INSERT INTO charging_sessions (station_id, created_at, completed_at)
            VALUES (:s,
                    now() - make_interval(days => :d),
                    now() - make_interval(days => :d) + make_interval(mins => :m))
        """), {"s": STATION, "d": 7 * w, "m": minutes})


def _slot(c, procedure: str) -> dict:
    c.execute(text(_procedure_sql(procedure)))
    c.execute(text("CALL pg_temp.refresh_station_hourly_occupancy()"))
    row = c.execute(text("""
        SELECT avg_occupancy, occupancy_level
          FROM station_hourly_occupancy
         WHERE station_id = :s
           AND day_of_week = EXTRACT(ISODOW FROM now() AT TIME ZONE 'Asia/Jakarta')::INT
           AND hour_of_day = EXTRACT(HOUR  FROM now() AT TIME ZONE 'Asia/Jakarta')::INT
    """), {"s": STATION}).mappings().one()
    return {"occupancy": float(row["avg_occupancy"]), "level": row["occupancy_level"]}


@requires_db
def test_one_busy_week_in_four_is_a_quarter_not_the_whole(db):
    # 60 minutes on one of the four occurrences of this slot. One connector, so
    # capacity is 60 minutes per occurrence and 240 across the window.
    _sessions(db, [1])
    assert _slot(db, "_FULL_WINDOW_PROCEDURE")["occupancy"] == pytest.approx(25.0)


@requires_db
def test_the_old_divisor_called_that_same_slot_completely_full(db):
    # The same data, the same procedure body that shipped: 60/60 = 100%. This is
    # the defect, executed, so the fix above is measured against it rather than
    # asserted about it.
    _sessions(db, [1])
    assert _slot(db, "_DAYS_WITH_SESSIONS_PROCEDURE")["occupancy"] == pytest.approx(100.0)


@requires_db
def test_the_error_crosses_the_bands_a_driver_is_shown(db):
    # 25% is MODERATE and 100% is PEAK. The inflation is not a rounding
    # difference in a number nobody reads; it is a different word on the screen.
    _sessions(db, [1])
    assert _slot(db, "_FULL_WINDOW_PROCEDURE")["level"] == "MODERATE"
    assert _slot(db, "_DAYS_WITH_SESSIONS_PROCEDURE")["level"] == "PEAK"


@requires_db
def test_three_busy_weeks_divide_by_four_not_by_three(db):
    # Pins the constant itself. The old divisor would count three days and
    # report 100%; four occurrences is 75%, and only one of those is the mean of
    # what actually happened across the window.
    _sessions(db, [1, 2, 3])
    assert _slot(db, "_FULL_WINDOW_PROCEDURE")["occupancy"] == pytest.approx(75.0)
    assert _slot(db, "_DAYS_WITH_SESSIONS_PROCEDURE")["occupancy"] == pytest.approx(100.0)


@requires_db
def test_a_slot_busy_every_week_is_unchanged_by_the_fix(db):
    # The fix must not move a station that really is full. Four occurrences, all
    # busy: both divisors agree, which is why the bug survived review.
    _sessions(db, [1, 2, 3, 4])
    assert _slot(db, "_FULL_WINDOW_PROCEDURE")["occupancy"] == pytest.approx(100.0)
    assert _slot(db, "_DAYS_WITH_SESSIONS_PROCEDURE")["occupancy"] == pytest.approx(100.0)


@requires_db
def test_a_slot_that_never_saw_a_session_is_zero_not_null(db):
    # station_hourly_occupancy is read with `avg_occupancy IS NOT NULL`, so a
    # NULL here would silently drop the hour from the chart instead of showing
    # it as quiet. Four weeks of data and nothing happened IS a measurement.
    _sessions(db, [1])
    db.execute(text(_procedure_sql("_FULL_WINDOW_PROCEDURE")))
    db.execute(text("CALL pg_temp.refresh_station_hourly_occupancy()"))
    quiet = db.execute(text("""
        SELECT count(*) AS n, count(avg_occupancy) AS not_null,
               count(*) FILTER (WHERE avg_occupancy = 0) AS zero
          FROM station_hourly_occupancy WHERE station_id = :s
    """), {"s": STATION}).mappings().one()
    assert quiet["n"] == 7 * 24, "every slot must be written, not only the busy ones"
    assert quiet["not_null"] == 7 * 24
    assert quiet["zero"] == 7 * 24 - 1
