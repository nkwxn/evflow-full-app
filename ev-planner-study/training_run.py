"""What data produced a model, and where that gets written down.

TWO PROBLEMS THIS SOLVES, BOTH FOUND THE HARD WAY

An artifact records trained_at, n_samples and sklearn_version, which says when it
was fitted and with what library. It does not say what it was fitted ON. When
lu_commercial_share changed for 657 cells on 2026-08-25 there was no way to ask a
loaded model whether it had seen the old values or the new ones -- and a model
serving a feature distribution the table no longer holds returns confident,
well-formed, wrong numbers, which is the exact failure services/siting_model.py
was written to prevent for column order.

So every artifact now carries a fingerprint of its inputs, and /health compares
it against the live database.

The second problem is that nothing recorded a training run except stdout. Which
model beat which, on what data, and why one was kept lived in a terminal
scrollback until the window was closed.

WHY A JSONL FILE AND NOT A TRACKING SERVER

MLflow was considered and dropped. It answers this well, but it wants a server, a
backend store and an artifact store, and the VPS this runs on has 2.2 GB of
memory free and already carries six containers. More to the point, the whole need
here is "one appendable line per run that a human and a diff can both read" --
and a file does that with nothing to keep running, nothing to back up, and
nothing that can be down at the moment someone needs to retrain.

The file lives beside the scripts rather than in output/, which is gitignored: a
run record that disappears with the artifact it describes answers nothing.

If this ever needs experiment comparison across many runs, or a registry with
promotion stages, revisit it then -- the fields written here map onto MLflow's
params/metrics/tags directly, on purpose.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
from typing import Any, Dict, Optional

#: Beside the scripts, not under output/. See the module docstring.
RUN_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "training_runs.jsonl")


def _sha256_head(path: str, chunk: int = 1 << 20) -> Optional[str]:
    """First 16 hex of the file's SHA-256, or None if it is not there.

    Truncated because this is an identity check between two known files, not a
    defence against a forged one: 64 bits is far past the point where two grids
    collide by accident, and a short string stays readable in a log line.
    """
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()[:16]


def dataset_fingerprint(conn, grid_path: Optional[str] = None) -> Dict[str, Any]:
    """Identify the data a model is about to be fitted on.

    Cheap by construction -- four counts and one file hash -- because anything
    that costs real time gets skipped when someone is in a hurry, and a check
    that is skipped protects nothing.

    `conn` is an open SQLAlchemy connection. The counts are the things that
    actually move underneath a model: the grid rebuild (cells, built_at), the
    feature reload (the same built_at), and the supply refresh (stations,
    connectors), which is what feeds nearest_station_m and stations_2km.
    """
    from sqlalchemy import text

    row = conn.execute(text("""
        SELECT (SELECT count(*)            FROM planning_cells) AS cells,
               (SELECT max(built_at)       FROM planning_cells) AS cells_built_at,
               (SELECT count(*)            FROM stations)       AS stations,
               (SELECT count(*)            FROM connectors)     AS connectors
    """)).mappings().one()

    fp: Dict[str, Any] = {
        "cells": int(row["cells"] or 0),
        "cells_built_at": row["cells_built_at"].isoformat() if row["cells_built_at"] else None,
        "stations": int(row["stations"] or 0),
        "connectors": int(row["connectors"] or 0),
        "grid_sha256_16": _sha256_head(grid_path) if grid_path else None,
    }
    fp["digest"] = hashlib.sha256(
        json.dumps(fp, sort_keys=True).encode()).hexdigest()[:16]
    return fp


def describe_fingerprint(fp: Dict[str, Any]) -> str:
    """One line, for a log or a mismatch warning."""
    if fp.get("cells") is None:
        return f"unknown ({fp.get('note', 'no fingerprint recorded')})"
    return (f"{fp['cells']:,} cells built {fp.get('cells_built_at')}, "
            f"{fp['stations']:,} stations / {fp['connectors']:,} connectors, "
            f"grid {fp.get('grid_sha256_16')} -> {fp['digest']}")


def fingerprints_match(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
    """Same data, ignoring anything not recorded on both sides."""
    if not a or not b:
        return False
    return a.get("digest") is not None and a.get("digest") == b.get("digest")


class _Run:
    """Accumulates one run, then appends it as a single line.

    Buffered rather than streamed so a run that dies halfway leaves no half
    record: an entry in this file should mean the run reached its end, and a
    refusal is an end.
    """

    def __init__(self, kind: str, name: str, path: str) -> None:
        self._path = path
        self._doc: Dict[str, Any] = {
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "run": name,
            "params": {},
            "metrics": {},
            "tags": {},
            "artifact": None,
        }

    def param(self, key: str, value: Any) -> None:
        self._doc["params"][key] = value

    def metric(self, key: str, value: float, step: Optional[int] = None) -> None:
        self._doc["metrics"][key] = round(float(value), 6)

    def tag(self, key: str, value: Any) -> None:
        self._doc["tags"][key] = value

    def saved(self, name: str, artifact_path: str) -> None:
        """Record that this run produced a servable artifact.

        The hash is what ties a file on a server back to the row that describes
        it. Without it, "which run made the model currently deployed" is a
        question nobody can answer once two runs share a day.
        """
        self._doc["artifact"] = {
            "name": name,
            "path": os.path.relpath(artifact_path, os.path.dirname(self._path)),
            "bytes": os.path.getsize(artifact_path) if os.path.exists(artifact_path) else None,
            "sha256_16": _sha256_head(artifact_path),
        }

    def _flush(self) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(self._doc, sort_keys=True) + "\n")
        art = self._doc["artifact"]
        print(f"  run recorded in {os.path.basename(self._path)}"
              + (f" (artifact {art['sha256_16']})" if art else " (no artifact)"),
              flush=True)


@contextlib.contextmanager
def track(kind: str, run_name: str, path: str = RUN_LOG):
    """Open a run, and write it out however it ends.

    Never raises for a bookkeeping reason. A retrain that fails because a log
    file could not be written would teach everyone to work around the log, and a
    step people route around is worse than one that is absent.
    """
    run = _Run(kind, run_name, path)
    try:
        yield run
    finally:
        try:
            run._flush()
        except OSError as exc:
            print(f"  could not write the run log ({exc}); training result stands",
                  flush=True)
