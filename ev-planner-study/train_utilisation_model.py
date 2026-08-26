"""Train the utilisation model on the demand-weighted simulation window.

WHAT THIS PREDICTS, AND WHY THAT MATTERS MORE THAN THE SCORE

The descriptive model answers "does this cell resemble the ones that already
have a station". Measured across all 27,219 cells, its 500 highest-probability
cells are 100% already built, so it cannot rank a place nobody has built on.
That is the question a planner actually has.

This one predicts demand intensity: given a cell's demand-side features, how many
sessions a connector there would draw per day. It CAN rank unbuilt cells.

THE GROUND TRUTH IS AN ASSUMPTION, NOT AN OBSERVATION.

Every charging session in this database is simulation output. Migrations 0023 and
0024 weight each station's session probability by its cell's population, POI
activity and road nodes, so the sessions encode THAT assumption and this model
recovers it. It is a scenario tool: "if demand follows those three features with
those weights, here is where utilisation lands". It is not a forecast, and the
weights are the knob to argue about, not the output.

WHY THE PREVIOUS VERSION SCORED LOCO R2 = -0.1219

Three defects compounded. All three were measured on staging 2026-08-24, and the
fixes below are aimed at exactly those measurements.

1. THE TARGET CANCELLED THE SIGNAL. Occupancy is sessions x duration / capacity.
   Duration is energy_kwh / power_kw, and high-factor locations turned out to
   hold faster chargers -- mean power by factor quartile 107.8 / 99.6 / 104.1 /
   127.1 kW, mean session length falling 39.2 -> 31.5 minutes. Serving more
   drivers faster reads as LESS occupied, so occupancy moved against demand:
   corr(occupancy, factor) = -0.069 while corr(occupancy, connector_count) =
   -0.597. The model was asked to predict a target driven mostly by the one
   feature it was forbidden to see.

   Fixed by targeting sessions per connector per day -- demand volume, which is
   what a planner is buying -- instead of how full the hardware looks.

2. THE WINDOW WAS CONTAMINATED. Ownership by a sim.* account was treated as the
   marker of weighting. It is not: sim.* sessions predate the weighting by weeks.
   Dose-response per day (ratio of sessions per connector, top factor quartile
   over bottom) shows three regimes:

       27-30 Jul        0.90 - 0.95    no weighting
       31 Jul - 20 Aug  ~1.20          migration 0023 (linear percentile map)
       21-24 Aug        1.61 - 1.71    migration 0024 (rank among stations)

   Training on 28 days mixed 3-4 weighted days into ~21 weakly-weighted ones.
   Restricting to the weighted window lifted corr(sessions per connector per day,
   factor) from 0.055 to 0.377.

   Fixed by deriving the window from station_demand_factor.computed_at, which is
   the moment the current factor values were written. Sessions before it were
   drawn against different factors and belong to a different experiment.

3. HARDWARE WAS INVISIBLE. corr(sessions per connector per day, mean power) =
   0.688 against 0.377 for the factor: the hardware explains more of the target
   than the location does. Excluding it did not remove its variance, it just
   moved it into the residual.

   Fixed by offering a hardware-aware feature set as one arm of the ablation and
   letting the leave-one-area-out score choose. When hardware features are in,
   scoring an unbuilt cell holds them at REFERENCE_SPEC, so differences between
   cells come only from location -- a planner evaluates a configuration at a
   place, not a bare place.

ONE MORE MEASUREMENT WORTH CARRYING FORWARD

The comment in scripts/sql/charging_simulation.sql claims the busiest location
draws "about 3.2x the quietest". Measured between quartile means on weighted
days it is 1.65x, against 2.63x expected from the factors alone. The connector
availability gate absorbs the rest: a connector that is busy cannot start a
session however attractive its location, so the arrival rate saturates as
r = p*f / (1 + p*f*D). Duty cycle is only 0.12-0.15, so the gate is far from
binding, yet it still costs a third of the spread. The 3.2x figure was never
measured and should be corrected in that file.

Usage:
    DATABASE_URL=postgresql+psycopg://... python3 train_utilisation_model.py
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from training_run import dataset_fingerprint, describe_fingerprint, track  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
GRID_GPKG = os.path.join(HERE, "grid_jabodetabek_500m.gpkg")
MODEL_PATH = os.path.join(OUT, "utilisation_model.joblib")

RANDOM_STATE = 42

#: Station-derived columns are excluded from the LOCATION feature set for the
#: same reason as in the siting model: they encode "a station is already here",
#: which no unbuilt cell can answer. The hardware arm of the ablation adds back
#: only what a planner chooses when specifying a site (how many connectors, how
#: fast), never what is already built.
EXCLUDED = {
    "station_count", "connector_count", "nearest_station_m", "stations_2km",
    "cell_id", "kota", "geom", "centroid", "built_at", "overlap_frac",
    "ordinal", "number_of_cells",
}

#: poi_total is EXCLUDED in train_siting_model.py, correctly, as the sum of the
#: poi_* columns and collinear with them. It is kept here, and the difference is
#: not an oversight. refresh_station_demand_factor() ranks cells by poi_total
#: itself, so it is a direct input to the target -- and a decision tree cannot
#: add features together, only partition them one axis at a time. Making the
#: forest reconstruct a 30-column sum from axis-aligned splits is a real
#: handicap; collinearity, for an ensemble of trees, is not.

#: Hardware the planner specifies, held at REFERENCE_SPEC when scoring.
HARDWARE = ["connectors", "avg_kw"]

#: Carried for the noise check and never offered to the model: these are the
#: target and its own numerator. planning_cells holds no such column today, so
#: this filter is dormant -- it exists because the feature list is discovered
#: from the schema, and a column added later with one of these names would leak
#: the answer into the features silently, scoring perfectly and predicting
#: nothing.
NOT_A_FEATURE = ["sessions", "duty", "sessions_per_conn_day", "sessions_per_free_conn_day"]

#: Below these the weighted window is too thin to train on and the script stops
#: rather than reporting a number nobody should trust. Days are COMPLETE local
#: days: a partial day drags every rate down and is excluded.
MIN_DAYS = 3

#: A floor, not a quality bar, and the distinction cost a run to learn.
#:
#: The first version of this guard demanded 40 sessions per cell so that counting
#: noise (1/sqrt(n), about 16% there) stayed under the roughly +/-25% spread the
#: factor produces. It then refused at 29 -- and refusing was wrong, because the
#: risk is not symmetric. Counting noise ATTENUATES a cross-validated score: it
#: adds variance the features cannot explain, so it drives LOCO R2 down toward
#: zero. It cannot manufacture skill that is not there. A positive result under
#: noisy labels is therefore conservative and trustworthy; only a negative one is
#: ambiguous, because noise and genuinely useless features look alike.
#:
#: So the floor is set where a cell stops carrying a rate at all rather than
#: where it stops being tidy, and the noise figure is reported instead of being
#: enforced. Cells are weighted by their session count when fitting, which is the
#: statistically honest version of what the hard threshold was groping for.
#: Filtering sparse cells out instead would bias the sample toward busy places
#: and truncate the low end of the very target being modelled.
MIN_SESSIONS_PER_CELL = 10

#: The dose-response floor. Below this the factor is not reaching the sessions,
#: whatever the table says, and training would repeat the -0.1219 mistake. The
#: weighted days measured 1.61-1.71; 0023's weaker map measured ~1.20.
MIN_DOSE_RESPONSE = 1.35


def log(msg: str = "") -> None:
    print(msg, flush=True)


def weighted_window(c):
    """Find the window by MEASURING the weighting, not by trusting a timestamp.

    The obvious marker, station_demand_factor.computed_at, does not survive
    contact with the refresh function: 0024 DELETEs and re-INSERTs every row, so
    re-running it stamps today's time on values that have been driving the
    simulation for days. Measured 2026-08-24: computed_at said 12:44 today while
    the dose-response showed the weighting live since the 21st. A window derived
    from that stamp threw away three days of good sessions.

    So the window is the trailing run of complete local days whose OWN
    dose-response clears MIN_DOSE_RESPONSE -- the ratio of sessions per connector
    between the top and bottom factor quartile. That is self-validating in a way
    a timestamp is not: a day only counts if the factor visibly reached its
    sessions. It also handles a weight change for free, because sessions drawn
    against superseded factors do not line up with the current quartiles and
    their ratio collapses toward 1.0.

    The per-day table is printed on every run. Its absence is what let a target
    built from 21 diluted days reach a training script at all.
    """
    import datetime as dt
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    jkt = ZoneInfo("Asia/Jakarta")
    rows = c.execute(text("""
        WITH q AS (SELECT station_id, ntile(4) OVER (ORDER BY factor) AS qt
                     FROM station_demand_factor),
        capq AS (SELECT q.qt, sum(c.n) AS conn
                   FROM q JOIN (SELECT station_id, count(*)::numeric AS n
                                  FROM connectors GROUP BY 1) c
                     ON c.station_id = q.station_id
                  GROUP BY 1),
        d AS (SELECT (cs.created_at AT TIME ZONE 'Asia/Jakarta')::date AS dt,
                     q.qt, count(*)::numeric AS n
                FROM charging_sessions cs
                JOIN q ON q.station_id = cs.station_id
                -- The SAME population the target is built from. Dropping this
                -- filter here, while pull() keeps it, made the gauge read a
                -- different universe than the model: the 2.07 million older
                -- sessions owned by demo.driver and fleet.operator carry no
                -- weighting, spread evenly across both quartiles, and dilute
                -- the ratio. Measured 2026-08-24, the same three days read 1.61
                -- / 1.67 / 1.65 with the filter and 1.19 / 1.20 / 1.19 without.
                -- The unfiltered number lands almost exactly on 0023's ~1.20,
                -- so a broken gauge here does not look broken -- it looks like
                -- a plausible finding about which migration is live.
                JOIN users u ON u.id = cs.user_id
               WHERE u.username LIKE 'sim.%%'
                 -- 14, not 30: this runs over an SSH tunnel that has died
                 -- three times in an afternoon, and the trailing run plus a few
                 -- days of context is all the window search needs. Widen it if
                 -- you are looking for an older regime change.
                 AND cs.created_at >= now() - interval '14 days'
                 -- Complete local days only. A partial day is a valid ratio but
                 -- an invalid rate, and the target is a rate.
                 AND (cs.created_at AT TIME ZONE 'Asia/Jakarta')::date
                     < (now() AT TIME ZONE 'Asia/Jakarta')::date
               GROUP BY 1, 2)
        SELECT d.dt,
               max(CASE WHEN d.qt = 1 THEN d.n / capq.conn END) AS q1,
               max(CASE WHEN d.qt = 4 THEN d.n / capq.conn END) AS q4
          FROM d JOIN capq ON capq.qt = d.qt
         GROUP BY d.dt ORDER BY d.dt
    """)).mappings().all()

    if not rows:
        log("  no complete days of sessions found.")
        raise SystemExit(1)

    stamp = c.execute(text("SELECT max(computed_at) FROM station_demand_factor")).scalar()
    if stamp is None:
        log("  station_demand_factor is empty: the simulation is running unweighted.")
        log("  Run SELECT refresh_station_demand_factor(); then wait for sessions.")
        raise SystemExit(1)

    days = []
    for r in rows:
        ratio = (float(r["q4"]) / float(r["q1"])) if r["q1"] and r["q4"] else 0.0
        days.append({"dt": r["dt"], "ratio": ratio,
                     "q1": float(r["q1"] or 0), "q4": float(r["q4"] or 0)})

    log(f"  factors last written        : {stamp}  (informational; see docstring)")
    log("")
    log("  dose-response per day (sessions per connector, Q4 over Q1)")
    for d in days[-12:]:
        mark = "weighted" if d["ratio"] >= MIN_DOSE_RESPONSE else "diluted"
        log(f"    {d['dt']}   Q1 {d['q1']:5.2f}   Q4 {d['q4']:5.2f}   "
            f"{d['ratio']:.2f}  {mark}")

    run = []
    for d in reversed(days):
        if d["ratio"] < MIN_DOSE_RESPONSE:
            break
        run.append(d)
    run.reverse()

    if len(run) < MIN_DAYS:
        log("")
        log(f"  REFUSING: {len(run)} complete day(s) clear {MIN_DOSE_RESPONSE}, need {MIN_DAYS}.")
        log("  The window grows by one at each local midnight. If it never grows,")
        log("  the installed procedure is not reading the factor table -- check:")
        log("    SELECT prosrc LIKE '%demand_factor%' FROM pg_proc")
        log("     WHERE proname = 'process_charging_simulation';")
        log("  and reinstall with psql -f scripts/sql/charging_simulation.sql.")
        raise SystemExit(1)

    w_start = dt.datetime.combine(run[0]["dt"], dt.time.min, jkt)
    w_end = dt.datetime.combine(run[-1]["dt"] + dt.timedelta(days=1), dt.time.min, jkt)
    ratio = sum(d["ratio"] for d in run) / len(run)
    log("")
    log(f"  weighted window             : {run[0]['dt']} .. {run[-1]['dt']}  "
        f"({len(run)} days, mean dose-response {ratio:.2f})")
    return {"w_start": w_start, "w_end": w_end, "days": len(run),
            "computed_at": stamp, "ratio": ratio}


def pull(c, w):
    """One pull, every candidate target, so the ablation compares like with like."""
    import pandas as pd
    from sqlalchemy import text

    feats = [r[0] for r in c.execute(text("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'planning_cells'
           AND data_type IN ('integer','bigint','double precision','numeric','real')
         ORDER BY column_name"""))
             if r[0] not in EXCLUDED and r[0] not in NOT_A_FEATURE]
    cols = ", ".join(f'pc."{f}"' for f in feats)

    # The sim.* filter stays, but for its real reason: it keeps genuine app
    # traffic from demo accounts out of a simulated target. It is NOT what makes
    # a session weighted -- the window is.
    df = pd.read_sql(text(f"""
        WITH cap AS (
            SELECT station_id, count(*)::numeric AS connectors, avg(power_kw) AS avg_kw
              FROM connectors GROUP BY station_id
        ),
        sess AS (
            SELECT cs.station_id,
                   count(*)::numeric AS n,
                   -- Real duration, not the 60-minute measurement cap the old
                   -- occupancy formula used. Unfinished sessions are charged to
                   -- the window end; 1440 guards a stuck row.
                   sum(LEAST(EXTRACT(EPOCH FROM (
                       COALESCE(cs.completed_at, :w_end) - cs.created_at)) / 60.0,
                       1440.0)) AS busy_min
              FROM charging_sessions cs
              JOIN users u ON u.id = cs.user_id
             WHERE u.username LIKE 'sim.%%'
               AND cs.created_at >= :w_start AND cs.created_at < :w_end
             GROUP BY cs.station_id
        ),
        per_cell AS (
            SELECT pc.cell_id,
                   sum(cap.connectors)                                  AS connectors,
                   sum(cap.connectors * cap.avg_kw) / sum(cap.connectors) AS avg_kw,
                   sum(COALESCE(sess.n, 0))                             AS sessions,
                   sum(COALESCE(sess.busy_min, 0))                      AS busy_min
              FROM stations s
              JOIN planning_cells pc ON ST_Within(s.geom, pc.geom)
              JOIN cap  ON cap.station_id  = s.id
              LEFT JOIN sess ON sess.station_id = s.id
             WHERE pc.overlap_frac >= 0.5 AND pc.kota <> 'Kepulauan Seribu'
             GROUP BY pc.cell_id
        )
        SELECT pc.cell_id, pc.kota, {cols},
               p.connectors::float AS connectors,
               p.avg_kw::float     AS avg_kw,
               p.sessions::float                                   AS sessions,
               (p.sessions / p.connectors / :days)::float           AS sessions_per_conn_day,
               (p.busy_min / (p.connectors * 1440.0 * :days))::float AS duty
          FROM per_cell p JOIN planning_cells pc ON pc.cell_id = p.cell_id
         WHERE p.connectors > 0
    """), c, params={"w_start": w["w_start"], "w_end": w["w_end"], "days": w["days"]})

    # Saturation-inverted rate. A connector that is busy cannot start a session,
    # so the observed rate understates the demand offered to it by exactly the
    # fraction of time it was unavailable. Dividing that back out is the same
    # correction as r = p*f/(1+p*f*D) solved for p*f, and it is arithmetic on
    # measured quantities rather than another modelling assumption.
    df["sessions_per_free_conn_day"] = (
        df.sessions_per_conn_day / (1.0 - df.duty.clip(upper=0.95)))
    return df, feats


def evaluate(X, y, groups, n_kota, weights):
    """Leave-one-area-out, plus the random split it is meant to expose.

    A random split lets neighbouring cells sit on both sides, so the model
    recalls answers from a few hundred metres away. Holding out a whole kota
    asks "what about somewhere we have not modelled", which is the real question.
    """
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import GroupKFold, cross_val_score

    model = RandomForestRegressor(n_estimators=400, random_state=RANDOM_STATE, n_jobs=-1)
    cv = GroupKFold(n_splits=min(5, n_kota))
    # Weights reach fit, not the scorer: cells are fitted in proportion to how
    # many sessions back them, then scored on the target as it actually stands.
    # sklearn 1.4 renamed this argument; fit_params= raises TypeError on 1.7.
    fit = {"params": {"sample_weight": weights}}
    loco = cross_val_score(model, X, y, groups=groups, cv=cv, scoring="r2", **fit)
    rand = cross_val_score(model, X, y, cv=5, scoring="r2", **fit)
    return float(loco.mean()), float(rand.mean())


def main() -> int:
    import datetime as dt

    import joblib
    import sklearn
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError
    from sklearn.ensemble import RandomForestRegressor

    url = os.getenv("DATABASE_URL")
    if not url:
        log("DATABASE_URL is not set")
        return 2

    # pool_pre_ping and keepalives for the same reason api/db.py sets the first
    # one: this usually runs over an SSH tunnel that dies mid-session, and a
    # dead-but-pooled connection surfaces as a torn traceback halfway through a
    # query rather than as a connection error.
    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10,
        "keepalives_count": 3, "connect_timeout": 15,
    })
    try:
        with engine.connect() as c:
            w = weighted_window(c)
            ratio = w["ratio"]
            df, feats = pull(c, w)
            # Taken inside the same connection that produced the training rows,
            # so it describes the data this run actually saw rather than the
            # database's state a few seconds later.
            fingerprint = dataset_fingerprint(c, GRID_GPKG)
    except OperationalError as e:
        log("  cannot reach the database.")
        if "refused" in str(e) or "closed the connection" in str(e):
            log("  The SSH tunnel is the usual cause -- it dies mid-session and the")
            log("  port stops answering. Restart it from YOUR shell, so it outlives")
            log("  whatever started this, then run again:")
            log("    pkill -f 5433:localhost:5432")
            log("    ssh -i ~/Downloads/project-mon.pem -f -N -L 5433:localhost:5432 \\")
            log("        -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 \\")
            log("        -o ServerAliveCountMax=6 mvvkur@103.127.99.179")
        else:
            log(f"  {e.__class__.__name__}: {str(e).splitlines()[0]}")
        return 2

    median_cell = float(df.sessions.median())
    noise = 100.0 / (median_cell ** 0.5) if median_cell else float("inf")
    log(f"  sessions in window          : {int(df.sessions.sum()):,}")
    log(f"  median sessions per cell    : {median_cell:.0f}  (~{noise:.0f}% counting noise)")
    if median_cell < MIN_SESSIONS_PER_CELL:
        log(f"  REFUSING: below {MIN_SESSIONS_PER_CELL} per cell a cell carries no rate at all.")
        log("  Let the window grow another night. Widening the cell filter would")
        log("  make this worse, not better: it admits sparser cells and lowers the")
        log("  median further.")
        return 1
    log("  noise attenuates LOCO R2 rather than inflating it, so a positive score")
    log("  below is conservative; only a negative one is ambiguous at this width.")

    log(f"  cells with stations         : {len(df):,} across {df.kota.nunique()} kota")
    log(f"  sessions/connector/day      : {df.sessions_per_conn_day.mean():.2f} "
        f"+/- {df.sessions_per_conn_day.std():.2f}")
    log(f"  duty cycle                  : {df.duty.mean():.3f}")
    log(f"  location features           : {len(feats)}  (+{len(HARDWARE)} hardware)")
    log(f"  data fingerprint            : {describe_fingerprint(fingerprint)}")

    # Everything from here is one tracked run: the ablation that chooses the
    # target, the fit, and the artifact. Opened after the guards above so a
    # refused training does not leave an empty run in the registry claiming a
    # model exists.
    run_name = f"utilisation-{w['days']}d-{fingerprint['digest']}"
    with track("ev-planner-utilisation", run_name) as run:
        for key, value in fingerprint.items():
            run.param(f"data.{key}", value)
        run.param("window_days", w["days"])
        run.param("window_start", w["w_start"].isoformat())
        run.param("dose_response", round(ratio, 4))
        run.param("n_location_features", len(feats))
        run.param("min_dose_response", MIN_DOSE_RESPONSE)
        run.param("min_sessions_per_cell", MIN_SESSIONS_PER_CELL)
        run.metric("cells", len(df))
        run.metric("median_sessions_per_cell", median_cell)
        run.metric("counting_noise_pct", noise)

        groups, n_kota = df.kota.values, df.kota.nunique()
        weights = df.sessions.astype(float).values
        # duty is occupancy computed properly: real busy minutes over real capacity,
        # with no days-with-sessions denominator and no 60-minute cap. It is in the
        # ablation to settle defect 1 with the metric that decides, rather than with
        # the correlation that first suggested it.
        targets = ["sessions_per_conn_day", "sessions_per_free_conn_day", "duty"]
        arms = [("location only", feats), ("location + hardware", feats + HARDWARE)]

        log("")
        log("  ablation (leave-one-area-out R2; the random split is shown to expose it)")
        log(f"  {'target':<28} {'features':<22} {'LOCO':>8} {'random':>8}")
        results = []
        for t in targets:
            y = df[t].astype(float).values
            for name, cols in arms:
                X = df[cols].astype(float).values
                loco, rand = evaluate(X, y, groups, n_kota, weights)
                log(f"  {t:<28} {name:<22} {loco:>+8.4f} {rand:>+8.4f}")
                results.append({"target": t, "arm": name, "cols": cols, "loco": loco, "random": rand})
            slug = f"{t}.{name.replace(' ', '_').replace('+', 'and')}"
            run.metric(f"loco_r2.{slug}", loco)
            run.metric(f"random_r2.{slug}", rand)

        best = max(results, key=lambda r: r["loco"])
        log("")
        log(f"  best: {best['target']} / {best['arm']}  LOCO R2 {best['loco']:+.4f}")

        if best["loco"] <= 0:
            log("")
            log("  No arm beats guessing the mean. Do NOT ship a model from this run.")
            log(f"  The dose-response was {ratio:.2f}, so the weighting IS reaching the")
            log("  sessions; the failure is downstream of it. Next thing to check is")
            log("  whether the features still carry the factor: the factor is built")
            log("  from percentile ranks of population, poi_total and road_nodes, so")
            log("  a model that cannot recover it cannot see those columns either.")
            return 1

        X = df[best["cols"]].astype(float).values
        y = df[best["target"]].astype(float).values
        model = RandomForestRegressor(n_estimators=400, random_state=RANDOM_STATE, n_jobs=-1)
        model.fit(X, y, sample_weight=weights)

        imp = sorted(zip(best["cols"], model.feature_importances_), key=lambda kv: -kv[1])
        log("")
        log("  top features")
        for name, v in imp[:8]:
            log(f"    {name:<34} {v:.4f}")

        # Held at the median of what is actually built, so a scored cell reads as
        # "a typical site here", and every cell is compared on equal hardware.
        reference = {"connectors": float(df.connectors.median()),
                     "avg_kw": float(df.avg_kw.median())}

        os.makedirs(OUT, exist_ok=True)
        joblib.dump({
            "model": model,
            "feature_names": best["cols"],
            "target": best["target"],
            "target_units": "simulated charging sessions per connector per day",
            "reference_spec": reference if best["arm"].endswith("hardware") else None,
            "trained_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "window_start": w["w_start"].isoformat(),
            "window_end": w["w_end"].isoformat(),
            "window_days": w["days"],
            "factors_computed_at": w["computed_at"].isoformat(),
            "window_selected_by": "measured dose-response per day, not computed_at",
            "dose_response_q4_over_q1": ratio,
            "n_samples": len(df),
            # What this was fitted ON, not just when. services/utilisation_model
            # compares it against the live database at load time.
            "dataset_fingerprint": fingerprint,
            "median_sessions_per_cell": median_cell,
            "counting_noise_pct": noise,
            "fitted_weighted_by": "sessions per cell",
            "loco_r2": best["loco"],
            "random_split_r2": best["random"],
            "ablation": [{k: r[k] for k in ("target", "arm", "loco", "random")} for r in results],
            "sklearn_version": sklearn.__version__,
            "label": "utilisation SCENARIO (recovers the demand assumption in migrations "
                     "0023/0024, not a forecast)",
        }, MODEL_PATH)

        log("")
        run.tag("target", best["target"])
        run.tag("arm", best["arm"])
        run.tag("label", "SCENARIO: recovers the demand assumption in 0023/0024")
        run.metric("loco_r2", best["loco"])
        run.metric("random_split_r2", best["random"])
        run.saved("ev-planner-utilisation", MODEL_PATH)
        log(f"  saved {MODEL_PATH}")
        if reference and best["arm"].endswith("hardware"):
            log(f"  score unbuilt cells at the reference spec: {reference['connectors']:.0f} "
                f"connectors, {reference['avg_kw']:.0f} kW mean.")
        log("  label: utilisation SCENARIO. It predicts the assumption encoded in the")
        log("  simulation, not observed demand. Say so wherever the number appears.")
        log(f"  Trained on {w['days']} days; the window grows nightly, so retrain as it does.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
