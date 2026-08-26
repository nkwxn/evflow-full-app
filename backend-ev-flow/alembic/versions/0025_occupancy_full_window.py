"""Divide occupancy by the days in the window, not the days that had a session.

WHAT WAS WRONG

The denominator was GREATEST(COUNT(DISTINCT occurred_on), 1) -- the number of
days on which that (station, day_of_week, hour) slot saw any session at all. A
slot with no session on a given Monday did not pull its average down; it
vanished from the divisor.

So the figure answered "when this station is busy at 09:00 on a Monday, how busy
is it" while the chart presents it as "at 09:00 on a Monday, how busy is this
station". A conditional mean wearing an unconditional label, and it can only ever
read too high.

THE SIZE OF IT

Measured on staging 2026-08-24 over the 28-day window, per station: mean
occupancy 38.10% under the old denominator against 16.44% under this one. It
also correlated -0.54 with connector count, because a station with many
connectors spreads its sessions over more slots and so has fewer empty days
removed from its divisor than a small one -- the bias is not even uniform, it
favours small stations.

WHY THIS IS NOT COSMETIC

api/stations_repo.get_hourly_occupancy classifies every hour with fixed
thresholds: >= 80 PEAK, >= 50 BUSY, >= 20 MODERATE, else LOW. A figure inflated
by roughly 2.3x walks hours up one or two bands, so the driver app has been
telling people a station is MODERATE or BUSY at hours when it was LOW. The
classification is stored in the table by this same procedure, so the labels are
wrong at rest and not only in the read path.

WHY THE NEW DENOMINATOR IS A CONSTANT

The window is 28 days, which is exactly four weeks, so each (day_of_week, hour)
pair occurs exactly four times inside it -- three whole occurrences plus two
halves at the boundaries, since the window starts and ends at the same time of
day. The divisor is therefore the window length in weeks, and it is derived from
the window rather than written as a 4 so the two cannot drift apart if the window
is ever changed.

A slot with no sessions now records 0.0, which is what it is: we have four weeks
of data and nothing happened there. Previously it recorded 0.0 too, via the
COALESCE, so nothing changes for a slot that was empty on ALL four days. What
changes is the slot that was busy on one Monday and empty on three.

WHAT THIS DOES NOT FIX

Every session behind these numbers is simulation output (see
scripts/sql/charging_simulation.sql). This migration makes the arithmetic honest;
it does not make the data observed.

Existing rows are corrected by running CALL refresh_station_hourly_occupancy();
after this migration, as with 0019. It is not called here: the procedure rewrites
every slot for every station over a 28-day window of charging_sessions, which is
minutes of work and a long lock on a table the API reads.

The id is short for a reason. alembic_version.version_num is varchar(32), and
alembic updates it in the SAME transaction as the migration body, so an id that
does not fit rolls the whole migration back AFTER the log line says it ran --
which is the most confusing way this can fail. The first attempt at this file
was "0025_occupancy_full_window_denominator", 38 characters, and it did exactly
that. 0024_demand_factor_station_rank is 31, so the ceiling has been one
character away for a while; tests/test_migration_ids.py now guards it.

Revision ID: 0025_occupancy_full_window
Revises: 0024_demand_factor_station_rank
"""
from alembic import op

revision = "0025_occupancy_full_window"
down_revision = "0024_demand_factor_station_rank"
branch_labels = None
depends_on = None


_FULL_WINDOW_PROCEDURE = """
CREATE OR REPLACE PROCEDURE refresh_station_hourly_occupancy()
LANGUAGE plpgsql
AS $$
DECLARE
    -- One place, so the window and its slot count cannot drift apart. Change
    -- the days and the divisor follows; write a bare 4 and it will not.
    window_days      CONSTANT NUMERIC := 28;
    slot_occurrences CONSTANT NUMERIC := 28 / 7.0;
BEGIN
    INSERT INTO station_hourly_occupancy (
        station_id, day_of_week, hour_of_day,
        avg_occupancy, occupancy_level, last_updated
    )
    WITH station_capacity AS (
        SELECT station_id, COUNT(*)::NUMERIC AS total_connectors
        FROM connectors
        GROUP BY station_id
    ),
    hourly_slots AS (
        SELECT sc.station_id, sc.total_connectors,
               d.dow AS day_of_week, h.hour_val AS hour_of_day
        FROM station_capacity sc
        CROSS JOIN generate_series(1, 7)  AS d(dow)
        CROSS JOIN generate_series(0, 23) AS h(hour_val)
    ),
    session_overlaps AS (
        SELECT
            cs.station_id,
            EXTRACT(ISODOW FROM cs.created_at AT TIME ZONE 'Asia/Jakarta')::INT AS day_of_week,
            EXTRACT(HOUR  FROM cs.created_at AT TIME ZONE 'Asia/Jakarta')::INT  AS hour_of_day,
            -- GREATEST floors a negative span. Without it a row whose
            -- completed_at precedes created_at drives the sum below zero and the
            -- column's CHECK aborts the whole refresh.
            GREATEST(LEAST(
                EXTRACT(EPOCH FROM (COALESCE(cs.completed_at, NOW()) - cs.created_at)) / 60.0,
                60.0
            ), 0) AS active_minutes
        FROM charging_sessions cs
        WHERE cs.created_at IS NOT NULL
          AND cs.created_at >= (NOW() - make_interval(days => window_days::INT))
    ),
    aggregated_occupancy AS (
        SELECT
            hs.station_id, hs.day_of_week, hs.hour_of_day,
            ROUND(
                LEAST(
                    COALESCE(
                        -- Divided by every occurrence of this slot in the
                        -- window, including the ones with no session. Counting
                        -- only the days that had one is what made this read
                        -- 38.10% where the truth was 16.44%.
                        SUM(so.active_minutes)
                          / NULLIF(hs.total_connectors * 60.0 * slot_occurrences, 0)
                        * 100.0,
                        0.0
                    ),
                    100.0
                )::NUMERIC,
                2
            ) AS calculated_avg_occupancy
        FROM hourly_slots hs
        LEFT JOIN session_overlaps so
               ON hs.station_id  = so.station_id
              AND hs.day_of_week = so.day_of_week
              AND hs.hour_of_day = so.hour_of_day
        GROUP BY hs.station_id, hs.day_of_week, hs.hour_of_day, hs.total_connectors
    )
    SELECT
        station_id, day_of_week, hour_of_day,
        calculated_avg_occupancy,
        CASE
            WHEN calculated_avg_occupancy >= 80 THEN 'PEAK'
            WHEN calculated_avg_occupancy >= 50 THEN 'BUSY'
            WHEN calculated_avg_occupancy >= 20 THEN 'MODERATE'
            ELSE 'LOW'
        END,
        NOW()
    FROM aggregated_occupancy
    ON CONFLICT (station_id, day_of_week, hour_of_day)
    DO UPDATE SET
        avg_occupancy   = EXCLUDED.avg_occupancy,
        occupancy_level = EXCLUDED.occupancy_level,
        last_updated    = EXCLUDED.last_updated;
END;
$$
"""

#: 0019's body, restored verbatim on downgrade. Reverting puts the conditional
#: mean back, which is wrong but is what shipped, and a downgrade that installs
#: something neither release ever ran is worse than one that is faithful.
_DAYS_WITH_SESSIONS_PROCEDURE = """
CREATE OR REPLACE PROCEDURE refresh_station_hourly_occupancy()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO station_hourly_occupancy (
        station_id, day_of_week, hour_of_day,
        avg_occupancy, occupancy_level, last_updated
    )
    WITH station_capacity AS (
        SELECT station_id, COUNT(*)::NUMERIC AS total_connectors
        FROM connectors
        GROUP BY station_id
    ),
    hourly_slots AS (
        SELECT sc.station_id, sc.total_connectors,
               d.dow AS day_of_week, h.hour_val AS hour_of_day
        FROM station_capacity sc
        CROSS JOIN generate_series(1, 7)  AS d(dow)
        CROSS JOIN generate_series(0, 23) AS h(hour_val)
    ),
    session_overlaps AS (
        SELECT
            cs.station_id,
            EXTRACT(ISODOW FROM cs.created_at AT TIME ZONE 'Asia/Jakarta')::INT AS day_of_week,
            EXTRACT(HOUR  FROM cs.created_at AT TIME ZONE 'Asia/Jakarta')::INT  AS hour_of_day,
            (cs.created_at AT TIME ZONE 'Asia/Jakarta')::date  AS occurred_on,
            GREATEST(LEAST(
                EXTRACT(EPOCH FROM (COALESCE(cs.completed_at, NOW()) - cs.created_at)) / 60.0,
                60.0
            ), 0) AS active_minutes
        FROM charging_sessions cs
        WHERE cs.created_at IS NOT NULL
          AND cs.created_at >= (NOW() - INTERVAL '28 days')
    ),
    aggregated_occupancy AS (
        SELECT
            hs.station_id, hs.day_of_week, hs.hour_of_day,
            ROUND(
                LEAST(
                    COALESCE(
                        SUM(so.active_minutes)
                          / NULLIF(hs.total_connectors * 60.0
                                   * GREATEST(COUNT(DISTINCT so.occurred_on), 1), 0)
                        * 100.0,
                        0.0
                    ),
                    100.0
                )::NUMERIC,
                2
            ) AS calculated_avg_occupancy
        FROM hourly_slots hs
        LEFT JOIN session_overlaps so
               ON hs.station_id  = so.station_id
              AND hs.day_of_week = so.day_of_week
              AND hs.hour_of_day = so.hour_of_day
        GROUP BY hs.station_id, hs.day_of_week, hs.hour_of_day, hs.total_connectors
    )
    SELECT
        station_id, day_of_week, hour_of_day,
        calculated_avg_occupancy,
        CASE
            WHEN calculated_avg_occupancy >= 80 THEN 'PEAK'
            WHEN calculated_avg_occupancy >= 50 THEN 'BUSY'
            WHEN calculated_avg_occupancy >= 20 THEN 'MODERATE'
            ELSE 'LOW'
        END,
        NOW()
    FROM aggregated_occupancy
    ON CONFLICT (station_id, day_of_week, hour_of_day)
    DO UPDATE SET
        avg_occupancy   = EXCLUDED.avg_occupancy,
        occupancy_level = EXCLUDED.occupancy_level,
        last_updated    = EXCLUDED.last_updated;
END;
$$
"""


def upgrade() -> None:
    op.execute(_FULL_WINDOW_PROCEDURE)


def downgrade() -> None:
    op.execute(_DAYS_WITH_SESSIONS_PROCEDURE)
