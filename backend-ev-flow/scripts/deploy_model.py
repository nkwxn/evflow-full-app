"""Put a trained artifact where the deployed API can read it, or refuse.

WHY THIS EXISTS

Measured 2026-08-26, neither deployed container held a model:

    podman exec evflow-api-staging  -> NO_MODEL_DIR, SITING_MODEL_PATH unset
    podman exec evflow-api          -> NO_MODEL_DIR

Containerfile copies api/, alembic/, scripts/ and ev_dataset.zip, not
ev-planner-study/output/, and that directory is gitignored besides. The services
fall back to a path relative to the source tree, which resolves in a dev
checkout and nowhere else. So every planner ML endpoint answered 503 on staging
and production while the same code worked on a laptop, and nothing reported it.

WHY A MOUNT AND NOT A LAYER IN THE IMAGE

Baking the joblib into the image ties every retrain to an image rebuild and a
registry push. A read-only mount lets a retrain ship by copying one file. The
cost is that the mount has to exist, which is a one-time container recreation
this script will print rather than perform: recreating a running container on a
host that also serves production is not something a deploy script should decide
to do on its own.

WHAT IT REFUSES, AND WHY THAT IS THE POINT

Copying a file is the easy half. The half that matters is not copying the wrong
one:

  * an artifact with no dataset_fingerprint predates the provenance work, so
    nobody can say what it was fitted on
  * an artifact whose fingerprint does not match the target database was fitted
    on data that has since moved. sklearn will serve it happily and return
    confident, well-formed, wrong numbers -- the exact failure the feature-order
    check in services/siting_model.py exists to prevent, one level up

Both are refusals rather than warnings. A warning at deploy time is read once.

Usage:
    python3 -m scripts.deploy_model --artifact ../ev-planner-study/output/siting_model.joblib \
                                    --target staging
    python3 -m scripts.deploy_model --artifact ... --target staging --check-only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

#: Where the mount lands inside the container, and what the env var must say.
CONTAINER_DIR = "/models"

TARGETS = {
    "staging": {"container": "evflow-api-staging", "port": 8001, "database": "evflow_staging"},
    "production": {"container": "evflow-api", "port": 8000, "database": "evflow"},
}

#: Which env var each artifact is served through, keyed by the filename the
#: services expect. Kept here rather than inferred, so a renamed file fails
#: loudly instead of being mounted where nothing reads it.
ENV_FOR = {
    "siting_model.joblib": "SITING_MODEL_PATH",
    "utilisation_model.joblib": "UTILISATION_MODEL_PATH",
}


def ssh(host: str, key: str, command: str) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-i", key, host, command],
                          capture_output=True, text=True, timeout=120)


def artifact_fingerprint(path: Path) -> dict:
    import joblib
    a = joblib.load(path)
    fp = a.get("dataset_fingerprint")
    if not fp:
        raise SystemExit(
            f"{path.name} carries no dataset_fingerprint, so there is no way to say what it\n"
            f"was fitted on. Retrain with the current trainer, which records one.")
    return fp


def live_fingerprint(host: str, key: str, container: str, database: str) -> dict:
    """The same four counts the trainer took, read from the target database.

    The grid hash is deliberately not compared: the grid file is not on the
    server and hashing it here would compare a local file against a remote
    database, which proves nothing about either.
    """
    sql = ("SELECT json_build_object("
           "'cells', (SELECT count(*) FROM planning_cells),"
           "'cells_built_at', (SELECT max(built_at) FROM planning_cells),"
           "'stations', (SELECT count(*) FROM stations),"
           "'connectors', (SELECT count(*) FROM connectors))")
    r = ssh(host, key,
            f"podman exec -e PGPASSWORD=evflow evflow-db "
            f"psql -U evflow -d {database} -tAc \"{sql}\"")
    if r.returncode != 0:
        raise SystemExit(f"could not read the {database} fingerprint:\n{r.stderr.strip()}")
    return json.loads(r.stdout.strip())


def compare(artifact: dict, live: dict) -> list[str]:
    """Field-by-field, so a mismatch names what moved rather than saying 'differs'."""
    drift = []
    for key in ("cells", "stations", "connectors"):
        if artifact.get(key) != live.get(key):
            drift.append(f"  {key:<16} artifact {artifact.get(key)!r}  live {live.get(key)!r}")
    a_built, l_built = str(artifact.get("cells_built_at")), str(live.get("cells_built_at"))
    if a_built[:19] != l_built[:19]:
        drift.append(f"  {'cells_built_at':<16} artifact {a_built}  live {l_built}")
    return drift


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", required=True, type=Path)
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--host", default="mvvkur@103.127.99.179")
    ap.add_argument("--key", default=str(Path.home() / "Downloads" / "project-mon.pem"))
    ap.add_argument("--remote-dir", default="/home/mvvkur/models")
    ap.add_argument("--check-only", action="store_true",
                    help="Run every refusal and stop before copying anything.")
    args = ap.parse_args()

    if not args.artifact.exists():
        print(f"no such artifact: {args.artifact}", file=sys.stderr)
        return 2
    env_var = ENV_FOR.get(args.artifact.name)
    if not env_var:
        print(f"{args.artifact.name} is not a name any service reads. Expected one of: "
              f"{', '.join(sorted(ENV_FOR))}", file=sys.stderr)
        return 2

    t = TARGETS[args.target]
    print(f"artifact : {args.artifact}")
    print(f"target   : {args.target} ({t['container']}, database {t['database']})")

    fp = artifact_fingerprint(args.artifact)
    live = live_fingerprint(args.host, args.key, t["container"], t["database"])
    drift = compare(fp, live)
    if drift:
        print("\nREFUSING: the artifact was fitted on data this database no longer holds.")
        print("\n".join(drift))
        print("\nThe model would still answer, and every number would be confident and wrong.")
        print("Retrain against this database, or deploy to the one it was fitted on.")
        return 1
    print(f"fingerprint matches {t['database']}: {fp['cells']:,} cells, "
          f"{fp['stations']:,} stations, {fp['connectors']:,} connectors")

    mounts = ssh(args.host, args.key,
                 f"podman inspect {t['container']} --format '{{{{json .Mounts}}}}'")
    if CONTAINER_DIR not in (mounts.stdout or ""):
        print(f"\n{t['container']} has no {CONTAINER_DIR} mount, so a copied file would not be")
        print("visible to it. Adding a mount means recreating the container, which this")
        print("script will not do to a host that also serves production. Run, once, by hand:")
        print(f"\n  ssh {args.host} 'mkdir -p {args.remote_dir}'")
        print(f"  # then recreate {t['container']} from its current definition, adding:")
        print(f"  #   -v {args.remote_dir}:{CONTAINER_DIR}:ro,z")
        print(f"  #   -e SITING_MODEL_PATH={CONTAINER_DIR}/siting_model.joblib")
        print(f"  #   -e UTILISATION_MODEL_PATH={CONTAINER_DIR}/utilisation_model.joblib")
        print(f"\n  podman inspect {t['container']} --format '{{{{.Config.CreateCommand}}}}'")
        print("  prints the command it was created with, as a starting point.")
        return 1

    if args.check_only:
        print("\n--check-only: every guard passed, nothing copied")
        return 0

    print(f"\ncopying to {args.remote_dir}/{args.artifact.name}")
    ssh(args.host, args.key, f"mkdir -p {args.remote_dir}")
    scp = subprocess.run(["scp", "-i", args.key, str(args.artifact),
                          f"{args.host}:{args.remote_dir}/{args.artifact.name}"],
                         capture_output=True, text=True, timeout=300)
    if scp.returncode != 0:
        print(f"copy failed:\n{scp.stderr.strip()}", file=sys.stderr)
        return 1

    print(f"restarting {t['container']}")
    ssh(args.host, args.key, f"podman restart {t['container']}")

    # Verified from the outside, not assumed from a zero exit code. /health names
    # each model, so a mount that landed in the wrong place is visible here
    # rather than at the first planner request.
    probe = ssh(args.host, args.key,
                f"for i in $(seq 1 15); do "
                f"curl -sf --max-time 5 http://127.0.0.1:{t['port']}/health && break; sleep 2; done")
    print(f"\n/health: {probe.stdout.strip() or '(no answer)'}")
    if '"missing"' in probe.stdout or not probe.stdout.strip():
        print("the API is not reading the artifact; check the mount path and the env var",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
