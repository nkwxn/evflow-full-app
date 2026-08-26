"""Train the siting model on Jabodetabek data, and report the honest number.

The reference notebook (section 7) trains on six German cities, because when it
was written we held no POI, population or land-use features of our own. We hold
all three now, so this trains on ours.

WHAT THIS PREDICTS, AND WHAT THAT IS WORTH

The label is "does this cell contain a station". That makes this a DESCRIPTIVE
model: 1,080 of our 1,236 stations are PLN placements that follow PLN offices
and policy targets, so what it learns is partly PLN's siting logic rather than
demand. It is not a recommendation engine. The prescriptive model is the
utilisation model on the Zenodo labels, which is not built yet.

WHY station-derived columns are excluded
    nearest_station_m, stations_2km, station_count and connector_count are all
    computed FROM the stations that form the label. Training presence on them is
    leakage by construction and inflates every metric. EXCLUDED below holds them
    out; everything else numeric on planning_cells is used.

WHY leave-one-area-out is the headline
    A random split scores 0.927 and means almost nothing: neighbouring cells
    land on both sides of the split, so the model is largely looking up answers
    it has already seen nearby. Holding out a whole kota is the question a
    planner actually asks -- "what about somewhere we have not built yet" -- and
    it scores 0.801. Report that one.

Usage:
    DATABASE_URL=postgresql+psycopg://... python3 train_siting_model.py
    python3 train_siting_model.py --from-parquet      # reuse the saved pull
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from training_run import dataset_fingerprint, describe_fingerprint, track  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
GRID_GPKG = os.path.join(HERE, "grid_jabodetabek_500m.gpkg")

#: Below this the model is not worth serving.
#:
#: train_utilisation_model refuses to save when its LOCO R2 is not above zero;
#: this script had no gate at all and would write an artifact whatever the AUC,
#: so a bad retrain would silently replace a good model. 0.65 is deliberately
#: lenient -- the measured figure is 0.814 and the reference study reports 0.893,
#: so anything near this floor means something broke rather than drifted.
MIN_LOCO_AUC = 0.65
INPUT_PARQUET = os.path.join(OUT, "model_input_jabodetabek.parquet")
FINGERPRINT_PATH = os.path.join(OUT, "model_input_fingerprint.json")
MODEL_PATH = os.path.join(OUT, "siting_model.joblib")

RANDOM_STATE = 42  # fixed so the reported numbers are reproducible

#: Demand-side features are discovered from the schema rather than listed here.
#: The POI set grew from 17 categories to 30 in migration 0022, and a hardcoded
#: list would have kept training on the old 17 while the new columns sat unused
#: -- silently, since a shorter feature list produces no error, just a worse
#: model. poi_total is excluded because it is the sum of the others.
EXCLUDED = {
    # Derived FROM the stations that form the label. Training presence on these
    # is leakage by construction and inflates every metric below.
    "station_count", "connector_count", "nearest_station_m", "stations_2km",
    # Sum of the poi_* columns; collinear with them by definition.
    "poi_total",
    # Identifiers and geometry, not features.
    "cell_id", "kota", "geom", "centroid", "built_at", "overlap_frac",
}

FEATURE_SQL = """
    SELECT column_name FROM information_schema.columns
     WHERE table_name = 'planning_cells'
       AND data_type IN ('integer', 'bigint', 'double precision', 'numeric', 'real')
     ORDER BY column_name
"""

# The same filter the scoring API applies, so the model is trained on the
# population of cells the product actually ranks.
WHERE = "overlap_frac >= 0.5 AND kota <> 'Kepulauan Seribu'"


def log(msg: str = "") -> None:
    print(msg, flush=True)


def pull() -> "pd.DataFrame":  # noqa: F821
    import pandas as pd
    from sqlalchemy import create_engine, text

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set (or pass --from-parquet)", file=sys.stderr)
        sys.exit(2)
    engine = create_engine(url)
    with engine.connect() as c:
        numeric = [r[0] for r in c.execute(text(FEATURE_SQL))]
    feats = [c_ for c_ in numeric if c_ not in EXCLUDED]
    log(f"features discovered from the schema: {len(feats)} "
        f"({sum(1 for f in feats if f.startswith('poi_'))} POI categories)")
    sql = (f"SELECT cell_id, kota, {', '.join(feats)}, "
           f"(station_count > 0)::int AS has_station "
           f"FROM planning_cells WHERE {WHERE}")
    df = pd.read_sql(text(sql), engine)
    with engine.connect() as c:
        fp = dataset_fingerprint(c, GRID_GPKG)
    os.makedirs(OUT, exist_ok=True)
    df.to_parquet(INPUT_PARQUET, index=False)
    # Beside the parquet, so --from-parquet can still say what it is training on.
    # A cached pull with no provenance is the same problem one layer down.
    with open(FINGERPRINT_PATH, "w") as f:
        json.dump(fp, f, indent=2)
    log(f"pulled {len(df):,} cells -> {os.path.relpath(INPUT_PARQUET, HERE)}")
    return df


def main(from_parquet: bool) -> int:
    import pandas as pd
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 f1_score, roc_auc_score)

    df = pd.read_parquet(INPUT_PARQUET) if from_parquet else pull()
    try:
        with open(FINGERPRINT_PATH) as f:
            fingerprint = json.load(f)
    except (OSError, ValueError):
        # --from-parquet against a parquet older than this feature. Recorded as
        # unknown rather than omitted: a missing key reads as "nobody thought
        # about it", an explicit unknown reads as "the input predates the check".
        fingerprint = {"digest": "unknown", "note": "no fingerprint beside the parquet"}
    log(f"data fingerprint: {describe_fingerprint(fingerprint)}"
        if fingerprint.get("cells") is not None else
        "data fingerprint: unknown (parquet predates fingerprinting)")
    # One tracked run covering the model comparison, the ablation, the fit and
    # the artifact. The comparison is the part worth keeping: which four
    # estimators were tried and how they ranked is a decision, and until now it
    # lived in a terminal scrollback.
    run_name = f"siting-{fingerprint.get('digest', 'unknown')}"
    with track("ev-planner-siting", run_name) as run:
        for key, value in fingerprint.items():
            run.param(f"data.{key}", value)
        run.param("min_loco_auc", MIN_LOCO_AUC)

        cols = [c for c in df.columns if c not in ("cell_id", "kota", "has_station")]
        X, y = df[cols].fillna(0.0), df["has_station"]

        log(f"\n{len(df):,} cells x {len(cols)} features | positive class {y.mean():.1%} "
            f"({int(y.sum()):,} cells with a station) | {df.kota.nunique()} areas")
        log("reference for comparison: 10,824 German cells x 19 features, 11.3% positive")

        models = {
            "LogisticRegression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
            "KNN (k=15)":         make_pipeline(StandardScaler(), KNeighborsClassifier(15)),
            "RandomForest":       RandomForestClassifier(200, random_state=RANDOM_STATE, n_jobs=-1),
            "GradientBoosting":   GradientBoostingClassifier(random_state=RANDOM_STATE),
        }

        log("\n== random split (the flattering number) ==")
        Xtr, Xte, ytr, yte = train_test_split(
            X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)
        log(f"  {'model':<20}{'AUC':>8}{'PR-AUC':>9}{'F1':>7}{'bal.acc':>9}")
        best_random = 0.0
        for name, m in models.items():
            m.fit(Xtr, ytr)
            p, pred = m.predict_proba(Xte)[:, 1], m.predict(Xte)
            auc = roc_auc_score(yte, p)
            best_random = max(best_random, auc)
            log(f"  {name:<20}{auc:>8.3f}{average_precision_score(yte, p):>9.3f}"
                f"{f1_score(yte, pred):>7.3f}{balanced_accuracy_score(yte, pred):>9.3f}")
        log(f"  PR-AUC baseline (always predict 'no station'): {y.mean():.3f}")

        log("\n== leave-one-area-out (the honest number) ==")
        rows = []
        for kota in sorted(df.kota.dropna().unique()):
            tr, te = df.kota != kota, df.kota == kota
            if y[te].nunique() < 2 or te.sum() < 30:
                rows.append([kota, int(te.sum()), y[te].mean(), np.nan])
                continue
            m = RandomForestClassifier(200, random_state=RANDOM_STATE, n_jobs=-1).fit(X[tr], y[tr])
            rows.append([kota, int(te.sum()), y[te].mean(),
                         roc_auc_score(y[te], m.predict_proba(X[te])[:, 1])])
        loco = pd.DataFrame(rows, columns=["area", "cells", "positive_rate", "AUC"])
        log(f"  {'area':<24}{'cells':>7}{'positive':>10}{'AUC':>8}")
        for _, r in loco.iterrows():
            auc = f"{r.AUC:.3f}" if pd.notna(r.AUC) else "-"
            log(f"  {str(r.area)[:22]:<24}{r.cells:>7}{r.positive_rate:>10.1%}{auc:>8}")
        log(f"\n  leave-one-area-out mean AUC : {loco.AUC.mean():.3f}   <-- report this one")
        log(f"  random split (best)         : {best_random:.3f}")
        log("  German reference            : LOCO 0.893 / random 0.905")
        log("  The gap is the finding: our areas differ far more than German cities did.")

        # Ablation. RandomForest's own importance ranks population second, but a
        # model given ONLY population scores 0.507 across held-out areas -- a coin
        # flip. Impurity importance is not evidence of generalisation; this is.
        log("\n== which feature families actually transfer ==")
        fam = {
            "population only":            ["population"],
            "roads only":                 ["road_nodes", "road_length_m"],
            "land use only":              [c for c in cols if c.startswith("lu_")],
            "POI only":                   [c for c in cols if c.startswith("poi_")],
            "population + roads":         ["population", "road_nodes", "road_length_m"],
            "pop + roads + land use":     ["population", "road_nodes", "road_length_m"]
                                          + [c for c in cols if c.startswith("lu_")],
            "everything":                 cols,
        }
        abl = []
        for name, feats in fam.items():
            scores = []
            for kota in sorted(df.kota.dropna().unique()):
                tr, te = df.kota != kota, df.kota == kota
                if y[te].nunique() < 2 or te.sum() < 30:
                    continue
                m = RandomForestClassifier(120, random_state=RANDOM_STATE, n_jobs=-1) \
                    .fit(df.loc[tr, feats], y[tr])
                scores.append(roc_auc_score(y[te], m.predict_proba(df.loc[te, feats])[:, 1]))
            abl.append([name, len(feats), float(np.mean(scores))])
            run.metric(f"ablation_loco_auc.{name.replace(' ', '_')}", float(np.mean(scores)))
            log(f"  {name:<26}{len(feats):>4} feats{float(np.mean(scores)):>9.3f}")
        pd.DataFrame(abl, columns=["feature_set", "n_features", "loco_auc"]) \
            .to_csv(os.path.join(OUT, "ablation_jabodetabek.csv"), index=False)

        rf = RandomForestClassifier(200, random_state=RANDOM_STATE, n_jobs=-1).fit(X, y)
        imp = pd.Series(rf.feature_importances_, index=cols).sort_values(ascending=False)
        log("\n== top 10 by impurity importance (read alongside the ablation, not instead) ==")
        for k, v in imp.head(10).items():
            log(f"  {k:<26}{v:.4f}")

        imp.to_csv(os.path.join(OUT, "feature_importance_jabodetabek.csv"))
        loco.to_csv(os.path.join(OUT, "loco_jabodetabek.csv"), index=False)

        # Persist the fitted model for the API to serve. `rf` above is fitted on the
        # WHOLE dataset, not the 80% train split: the split exists to measure, and a
        # model that is going to be served should learn from everything it can.
        #
        # feature_names travels with the model and is not optional. sklearn predicts
        # on positional arrays, so a column order that differs from training produces
        # confident, silently wrong probabilities -- no exception, no warning, just
        # population being read as road_length. The loader refuses to predict unless
        # the order matches exactly.
        import joblib
        loco_auc = float(loco.AUC.mean())
        if loco_auc < MIN_LOCO_AUC:
            run.metric("loco_auc", loco_auc)
            run.tag("refused", "loco_auc below floor")
            log(f"\nREFUSING to save: LOCO AUC {loco_auc:.3f} is below {MIN_LOCO_AUC}.")
            log("The existing artifact is left in place. A figure this low means an")
            log("input changed, not that the model drifted -- check that planning_cells")
            log("was reloaded after the last grid rebuild and that the label still")
            log("comes from the merged station footprint.")
            return 1

        artifact = {
            "model": rf,
            "feature_names": list(cols),
            "trained_at": pd.Timestamp.utcnow().isoformat(),
            "n_samples": int(len(df)),
            "n_positive": int(y.sum()),
            "loco_auc": loco_auc,
            "random_split_auc": float(best_random),
            "label": "station presence (descriptive, not prescriptive -- see module docstring)",
            "sklearn_version": __import__("sklearn").__version__,
            # What this was fitted ON. Without it there is no way to ask a loaded
            # model whether it saw the pre-fix or post-fix land-use shares.
            "dataset_fingerprint": fingerprint,
        }
        run.metric("loco_auc", loco_auc)
        run.metric("random_split_auc", float(best_random))
        run.metric("n_samples", int(len(df)))
        run.metric("n_positive", int(y.sum()))
        run.tag("label", "descriptive: station presence, not a recommendation")
        joblib.dump(artifact, MODEL_PATH, compress=3)
        run.saved("ev-planner-siting", MODEL_PATH)
        log(f"\nmodel saved: {os.path.relpath(MODEL_PATH, HERE)} "
            f"({os.path.getsize(MODEL_PATH)/1024:.0f} KB, {len(cols)} features, "
            f"LOCO AUC {loco.AUC.mean():.3f})")
        log(f"\nwrote feature_importance_jabodetabek.csv, loco_jabodetabek.csv, "
            f"ablation_jabodetabek.csv to {os.path.relpath(OUT, HERE)}/")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-parquet", action="store_true",
                    help="reuse output/model_input_jabodetabek.parquet instead of querying")
    sys.exit(main(ap.parse_args().from_parquet))
