"""Spread a ranked shortlist of cells into a handful of suggested points.

WHY THIS IS NOT IN SQL ANY MORE

ST_ClusterKMeans did this inside the ranking query, which was fine while the pin
score and the heatmap colour were the same SQL expression. They are not any more:
suitability comes from a fitted model in the API process. Pushing 27,000 scores
back into Postgres to cluster them would need a VALUES list near psycopg's
parameter ceiling for the region-wide case but not for the radius case -- two
code paths that behave differently under load, which is worse than one that is
slightly slower. Here the pin score and the cell colour are literally the same
function call.

WHAT IT IS, HONESTLY

k-means on model outputs. The ranking and the selection are model work; the
spatial spreading is not machine learning in any meaningful sense and must not be
described as such in the report.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

#: ST_ClusterKMeans is deterministic for a given input order; sklearn's k-means
#: is not, and its default n_init picks the best of several random starts. Two
#: identical requests returning different pins reads to a planner as the
#: recommendation changing its mind, so both are pinned.
RANDOM_STATE = 0
N_INIT = 10


def _project(points: Sequence[Dict[str, Any]]) -> List[List[float]]:
    """Metres-ish, so that k-means measures ground distance rather than degrees.

    A degree of longitude is cos(latitude) of a degree of latitude. Skipping this
    stretches the map east-west and splits clusters along the wrong axis -- the
    PostGIS version had exactly this flaw, and correcting it is one line.
    """
    lats = [p["latitude"] for p in points]
    k = math.cos(math.radians(sum(lats) / len(lats)))
    return [[float(p["latitude"]), float(p["longitude"]) * k] for p in points]


def spread(points: Sequence[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Group `points` geographically and report each group at its best member.

    A cluster centroid can land in the middle of a river or on the wrong side of
    a toll road. An actual cell is somewhere a survey can be sent, so the pin is
    always a real cell -- the same reason the SQL version used DISTINCT ON.

    Cells that already hold a station are dropped before clustering, not scored
    down: proposing a site where one already stands is indefensible whatever it
    scores, and letting it compete would also let it capture a cluster and hide
    the best free cell near it.
    """
    free = [p for p in points if not (p.get("station_count") or 0)]
    if not free:
        return []
    for p in free:
        if p.get("latitude") is None or p.get("longitude") is None:
            raise ValueError(f"cell {p.get('cell_id')} has no latitude/longitude")

    k = max(1, min(int(k), len(free)))
    if k == 1:
        best = max(free, key=lambda p: (p["score"], p["cell_id"]))
        return [{**best, "cluster_id": 0, "cluster_size": len(free)}]

    from sklearn.cluster import KMeans

    # Sorting first makes the result independent of the order rows arrive in,
    # which n_init alone does not guarantee.
    free = sorted(free, key=lambda p: p["cell_id"])
    labels = KMeans(n_clusters=k, random_state=RANDOM_STATE,
                    n_init=N_INIT).fit_predict(_project(free))

    groups: Dict[int, List[Dict[str, Any]]] = {}
    for label, p in zip(labels, free):
        groups.setdefault(int(label), []).append(p)

    pins = [{**max(g, key=lambda p: (p["score"], p["cell_id"])),
             "cluster_id": cid, "cluster_size": len(g)}
            for cid, g in groups.items()]
    return sorted(pins, key=lambda p: (-p["score"], p["cell_id"]))
