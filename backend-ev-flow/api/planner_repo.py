"""All planning_cells SQL, isolated from the endpoints.

Scores are computed per request rather than stored. The whole point of the
weights being a planner control is that moving one changes the map, so a stored
score would freeze exactly the thing that has to stay live. Cost is not the
reason to store: the grid is 28,176 rows and the work is a window function plus
a weighted sum, which Postgres finishes well inside a request.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from .db import engine
from .services.planner_viewport import POI_CATEGORIES, Viewport, metric_column
from .services.site_scoring import SiteWeights, normalised_weights

#: Percentile rank per feature, computed across every cell that survives the
#: filter. `coverage` is capped at 10 km first: past that distance a cell is
#: unserved in any practical sense, and without the cap the far edge of Kabupaten
#: Bogor would stretch the scale and compress everywhere a driver actually is.
#:
#: NULL coalesces to the cap, not to zero. nearest_station_m is NULL only when no
#: station exists to measure from, which means MAXIMALLY unserved; coalescing to
#: 0 metres said "a station is exactly here" and inverted the coverage term for
#: every cell. Never observed in production, where 1,237 stations make the column
#: always populated -- and invisible there for exactly that reason.
_RANKED = """
    WITH filtered AS (
        SELECT * FROM planning_cells
         WHERE overlap_frac >= :min_overlap
           AND kota <> ALL(:excluded_kota)
    ),
    ranked AS (
        SELECT cell_id, kota, centroid, population, poi_total, road_nodes,
               station_count, connector_count, nearest_station_m, stations_2km,
               PERCENT_RANK() OVER (ORDER BY LEAST(COALESCE(nearest_station_m, 10000), 10000))
                   AS r_coverage,
               PERCENT_RANK() OVER (ORDER BY population)  AS r_population,
               PERCENT_RANK() OVER (ORDER BY poi_total)   AS r_activity,
               PERCENT_RANK() OVER (ORDER BY road_nodes)  AS r_roads
          FROM filtered
    ),
    scored AS (
        SELECT *,
               round((r_coverage   * :w_coverage
                    + r_population * :w_population
                    + r_activity   * :w_activity
                    + r_roads      * :w_roads)::numeric, 4) AS score
          FROM ranked
    )
"""

# Sea-separated cells are unreachable by road, so they are excluded from
# candidate generation by default rather than left to distort cluster centres.
DEFAULT_EXCLUDED_KOTA = ["Kepulauan Seribu"]


def _weight_params(weights: SiteWeights) -> dict:
    w = normalised_weights(weights)
    return {f"w_{name}": value for name, value in w.items()}


def score_cells(weights: SiteWeights, limit: int = 50, min_overlap: float = 0.5,
                excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Highest scoring cells under the given weights, best first."""
    params = _weight_params(weights)
    params.update(limit=limit, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """
        SELECT cell_id, kota, score,
               ST_Y(centroid) AS latitude, ST_X(centroid) AS longitude,
               population, poi_total, road_nodes,
               station_count, connector_count,
               round(nearest_station_m::numeric, 0) AS nearest_station_m, stations_2km
          FROM scored
      ORDER BY score DESC, cell_id
         LIMIT :limit
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def candidate_sites(weights: SiteWeights, clusters: int = 15,
                    quantile: float = 0.90, min_overlap: float = 0.5,
                    excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Cluster the top-scoring cells into a handful of suggested points.

    ST_ClusterKMeans groups the qualifying cells geographically, and each group
    is reported at its highest scoring member rather than at its centroid. A
    centroid can land in the middle of a river or on the wrong side of a toll
    road; an actual cell is somewhere a survey can be sent.
    """
    params = _weight_params(weights)
    params.update(clusters=clusters, quantile=quantile, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """,
    top AS (
        SELECT * FROM scored
         WHERE score >= (SELECT percentile_cont(:quantile) WITHIN GROUP (ORDER BY score) FROM scored)
    ),
    clustered AS (
        SELECT *, ST_ClusterKMeans(centroid, LEAST(:clusters, (SELECT count(*)::int FROM top)))
                    OVER () AS cluster_id
          FROM top
    ),
    best_per_cluster AS (
        SELECT DISTINCT ON (cluster_id) *
          FROM clustered
      ORDER BY cluster_id, score DESC, cell_id
    )
        SELECT cluster_id, cell_id, kota, score,
               ST_Y(centroid) AS latitude, ST_X(centroid) AS longitude,
               population, poi_total, station_count,
               round(nearest_station_m::numeric, 0) AS nearest_station_m, stations_2km,
               (SELECT count(*) FROM clustered c2 WHERE c2.cluster_id = best_per_cluster.cluster_id) AS cluster_size
          FROM best_per_cluster
      ORDER BY score DESC
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def candidate_sites_in_radius(weights: SiteWeights, lat: float, lon: float,
                              radius_km: float, clusters: int = 8,
                              min_overlap: float = 0.5,
                              excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """The best cells within radius_km of a point, scored against the whole region.

    WHY THE CIRCLE IS APPLIED AFTER SCORING, NOT BEFORE

    This is the whole point of the function. PERCENT_RANK in _RANKED runs over
    every cell in Jabodetabek, and only then is the circle applied. Filter first
    and the ranks recompute inside the circle, so the best cell in a quiet
    suburb scores exactly like the best cell in Sudirman and the planner has no
    way to tell a strong area from a weak one. Scoring globally and filtering
    afterwards means 62 means the same thing everywhere.

    WHY THERE IS NO QUANTILE GATE HERE

    The region-wide version keeps only cells above the 90th percentile, which is
    right when the answer is "the best fifteen places in Jabodetabek". Inside a
    3 km circle that gate usually leaves nothing, and an empty answer reads as
    "we found no candidates" when the truth is "none of these clears a bar you
    were never shown". So every cell in the circle is eligible, and the score
    itself says how good each one really is.

    WHY THERE IS NO PERCENTILE COLUMN

    An earlier version returned each candidate's regional percentile, on the
    theory that "0.62, which is the 71st percentile" says more than "0.62". It
    does not, because the number is nearly constant. Measured on four very
    different 3 km circles -- Sudirman, Cibubur, Serpong and south Bogor -- the
    best cell scored at the 0.953, 0.991, 0.993 and 0.993 percentile. That is
    order statistics, not geography: take 115 cells from 27,219 and the maximum
    lands in the top percentile almost every time. Shipping it would have
    labelled every place a planner clicked as regionally top-tier.

    `score` is the comparable number, and it is comparable precisely because the
    ranks behind it are computed over the whole region. The same four circles
    scored 0.673, 0.722, 0.730 and 0.729, which is a real spread a planner can
    read.
    """
    params = _weight_params(weights)
    params.update(clusters=clusters, min_overlap=min_overlap,
                  lat=lat, lon=lon, radius_m=radius_km * 1000.0,
                  degrees=(radius_km * 1000.0) / 111_320.0,
                  excluded_kota=excluded_kota if excluded_kota is not None
                  else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """,
    centre AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g),
    in_circle AS (
        SELECT scored.* FROM scored, centre
         WHERE centroid && ST_Expand(centre.g, :degrees)
           AND ST_DWithin(centroid::geography, centre.g::geography, :radius_m)
    ),
    clustered AS (
        SELECT *, ST_ClusterKMeans(centroid,
                    GREATEST(LEAST(:clusters, (SELECT count(*)::int FROM in_circle)), 1))
                    OVER () AS cluster_id
          FROM in_circle
    ),
    best_per_cluster AS (
        SELECT DISTINCT ON (cluster_id) *
          FROM clustered
      ORDER BY cluster_id, score DESC, cell_id
    )
        SELECT cluster_id, cell_id, kota, score,
               ST_Y(centroid) AS latitude, ST_X(centroid) AS longitude,
               population, poi_total, station_count,
               round(nearest_station_m::numeric, 0) AS nearest_station_m, stations_2km,
               (SELECT count(*) FROM clustered c2
                 WHERE c2.cluster_id = best_per_cluster.cluster_id) AS cluster_size
          FROM best_per_cluster
      ORDER BY score DESC
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def features_for_cells(cell_ids: list[str], feature_names: list[str]) -> list[dict]:
    """Model features for specific cells, keyed by name.

    Columns are selected by name from the model's own feature list, so a
    retrained model with different features needs no change here. The names come
    from the artifact rather than from a caller, and every one is checked against
    the live schema before it reaches SQL -- a feature the table does not have is
    a mismatch worth an error, not a query that happens to work.

    Rows come back keyed by name, never positionally: see
    api/services/siting_model for why that distinction matters.
    """
    with engine.connect() as c:
        known = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'planning_cells'"""))}
        unknown = [f for f in feature_names if f not in known]
        if unknown:
            raise ValueError(
                f"the model expects {len(unknown)} column(s) planning_cells does not "
                f"have: {', '.join(unknown)}. The model is stale relative to the "
                f"schema; retrain it with ev-planner-study/train_siting_model.py")

        cols = ", ".join(f'"{f}"' for f in feature_names)
        rows = c.execute(text(f"""
            SELECT cell_id, kota, {cols}
              FROM planning_cells
             WHERE cell_id = ANY(:ids)
          ORDER BY cell_id
        """), {"ids": cell_ids}).mappings().all()
    return [dict(r) for r in rows]


def features_in_area(viewport: Viewport, feature_names: list[str],
                     limit: int = 30000, min_overlap: float = 0.5,
                     excluded_kota: Optional[list[str]] = None) -> tuple[list[dict], int]:
    """Model features for every cell inside an area the planner chose, and the true total.

    This is what makes prediction on demand rather than precomputed. The caller
    hands over whatever rectangle was drawn on the map and gets back the cells to
    run the model over, at the 500 m resolution the model was trained at.

    WHY THE AREA IS NOT COLLAPSED INTO A SINGLE ROW

    Summing an area's POI counts, population and road length into one feature
    vector and predicting once is the obvious way to answer "score this area",
    and it is wrong. Measured on this model, a 10 x 10 km selection puts 18 of
    its 33 additive features ABOVE the largest value anywhere in the training
    set, and a random forest cannot extrapolate -- it returns the leaf values of
    the most extreme cells it ever saw. That reads as 0.605 against a real
    per-cell mean of 0.040: fifteen times too high, with nothing to signal it.
    So the area is predicted cell by cell, and summarised afterwards.

    Returns the rows AND the number of cells that matched, which are different
    numbers once an area is large. Both are needed: a truncated answer that
    reports only what survived reads exactly like a complete one.

    Ordered by poi_total so a truncated area loses its quietest cells rather than
    an arbitrary geographic slice, matching what cells_geojson already does.
    """
    with engine.connect() as c:
        known = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'planning_cells'"""))}
        unknown = [f for f in feature_names if f not in known]
        if unknown:
            raise ValueError(
                f"the model expects {len(unknown)} column(s) planning_cells does not "
                f"have: {', '.join(unknown)}. The model is stale relative to the "
                f"schema; retrain it with ev-planner-study/train_siting_model.py")

        cols = ", ".join(f'"{f}"' for f in feature_names)
        # count(*) OVER () is evaluated before LIMIT, so it reports how many cells
        # the area really holds even when only some of them come back.
        rows = c.execute(text(f"""
            SELECT cell_id, kota, station_count, stations_2km, nearest_station_m,
                   {cols}, count(*) OVER () AS matched
              FROM planning_cells
             WHERE geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
               AND ST_Intersects(geom, ST_MakeEnvelope(:west, :south, :east, :north, 4326))
               AND overlap_frac >= :min_overlap
               AND kota <> ALL(:excluded_kota)
          ORDER BY poi_total DESC, cell_id
             LIMIT :limit
        """), {"west": viewport.west, "south": viewport.south,
               "east": viewport.east, "north": viewport.north,
               "min_overlap": min_overlap, "limit": limit,
               "excluded_kota": excluded_kota if excluded_kota is not None
               else DEFAULT_EXCLUDED_KOTA}).mappings().all()

    if not rows:
        return [], 0
    matched = int(rows[0]["matched"])
    return [{k: v for k, v in r.items() if k != "matched"} for r in rows], matched


def features_in_radius(lat: float, lon: float, radius_km: float,
                       feature_names: list[str], limit: int = 30000,
                       min_overlap: float = 0.5,
                       excluded_kota: Optional[list[str]] = None) -> tuple[list[dict], int]:
    """Model features for every cell within radius_km of a point the planner picked.

    A circle rather than the viewport, because "analyse around here" is the
    question a planner actually asks. A viewport answers "whatever happens to be
    on screen", which changes when they resize the window and cannot be compared
    between two locations.

    WHY THE BOUNDING BOX IS STILL IN THE QUERY

    ST_DWithin on geography is exact but cannot use the GIST index on a geometry
    column. The && against an expanded envelope narrows the scan by index first,
    then ST_DWithin trims the corners of that box to a true circle. Both are
    needed: the box alone would include cells up to 41% further away than asked
    for at the diagonal.

    station_count comes back alongside the features. The endpoint drops it before
    the model sees it, but the response needs it: this model ranks cells that
    ALREADY have a station at the very top, so a card that cannot tell the two
    apart presents existing sites as candidates.
    """
    with engine.connect() as c:
        known = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'planning_cells'"""))}
        unknown = [f for f in feature_names if f not in known]
        if unknown:
            raise ValueError(
                f"the model expects {len(unknown)} column(s) planning_cells does not "
                f"have: {', '.join(unknown)}. The model is stale relative to the "
                f"schema; retrain it with ev-planner-study/train_siting_model.py")

        cols = ", ".join(f'"{f}"' for f in feature_names)
        radius_m = radius_km * 1000.0
        # One degree of latitude is about 111.32 km. Longitude is shorter, so
        # using the latitude figure over-expands east-west, which is the safe
        # direction: the box must never be tighter than the circle it prefilters.
        degrees = radius_m / 111_320.0
        rows = c.execute(text(f"""
            WITH centre AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS g)
            SELECT cell_id, kota, station_count, stations_2km, nearest_station_m,
                   {cols}, count(*) OVER () AS matched
              FROM planning_cells, centre
             WHERE geom && ST_Expand(centre.g, :degrees)
               AND ST_DWithin(geom::geography, centre.g::geography, :radius_m)
               AND overlap_frac >= :min_overlap
               AND kota <> ALL(:excluded_kota)
          ORDER BY poi_total DESC, cell_id
             LIMIT :limit
        """), {"lat": lat, "lon": lon, "radius_m": radius_m, "degrees": degrees,
               "min_overlap": min_overlap, "limit": limit,
               "excluded_kota": excluded_kota if excluded_kota is not None
               else DEFAULT_EXCLUDED_KOTA}).mappings().all()

    if not rows:
        return [], 0
    matched = int(rows[0]["matched"])
    return [{k: v for k, v in r.items() if k != "matched"} for r in rows], matched


def features_for_unbuilt_cells(feature_names: list[str],
                               min_overlap: float = 0.5,
                               excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Model features for every cell in the region that has NO station.

    Used once, to find the highest resemblance any unbuilt cell reaches. That
    ceiling is what turns a bare 0.29 into "94% of the best anything unbuilt
    scores", and without it the number has no scale a planner can read.

    The same filter as the scored population, so the ceiling is drawn from the
    cells the product actually ranks rather than from Kepulauan Seribu or a
    sliver cell clipped by the region boundary.
    """
    with engine.connect() as c:
        known = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'planning_cells'"""))}
        unknown = [f for f in feature_names if f not in known]
        if unknown:
            raise ValueError(
                f"the model expects {len(unknown)} column(s) planning_cells does not "
                f"have: {', '.join(unknown)}. The model is stale relative to the "
                f"schema; retrain it with ev-planner-study/train_siting_model.py")

        cols = ", ".join(f'"{f}"' for f in feature_names)
        rows = c.execute(text(f"""
            SELECT {cols}
              FROM planning_cells
             WHERE station_count = 0
               AND overlap_frac >= :min_overlap
               AND kota <> ALL(:excluded_kota)
        """), {"min_overlap": min_overlap,
               "excluded_kota": excluded_kota if excluded_kota is not None
               else DEFAULT_EXCLUDED_KOTA}).mappings().all()
    return [dict(r) for r in rows]


def cells_geojson(viewport: Viewport, metric: str = "score",
                  weights: Optional[SiteWeights] = None, limit: int = 1500,
                  min_overlap: float = 0.5,
                  excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Cell polygons inside the viewport, carrying the value the map colours by.

    The map draws real polygons rather than a rendered image, so the geometry
    goes over the wire. That makes the row limit the thing standing between a
    zoomed-out request and a multi-megabyte response, which is why cells are
    ordered by the chosen value and the highest ones survive the cut: a truncated
    heatmap should lose its quiet cells, not an arbitrary slice of the map.

    `metric` never reaches SQL as caller text. It is resolved through the fixed
    table in planner_viewport, because a column name cannot be a bound parameter.
    """
    column = metric_column(metric)
    # Safe to interpolate: `column` is a value from METRIC_COLUMNS, not input.
    value_expr = "s.score" if column == "score" else f"p.{column}"

    params = _weight_params(weights or SiteWeights())
    params.update(west=viewport.west, south=viewport.south,
                  east=viewport.east, north=viewport.north,
                  limit=limit, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + f"""
        SELECT s.cell_id, s.kota, s.score, {value_expr} AS value,
               -- 6 decimals is about 11 cm, far finer than a 500 m cell needs.
               -- The default 15 nearly doubles the payload for no visible gain.
               ST_AsGeoJSON(p.geom, 6) AS geometry,
               s.population, s.poi_total, s.station_count,
               round(s.nearest_station_m::numeric, 0) AS nearest_station_m
          FROM scored s
          JOIN planning_cells p ON p.cell_id = s.cell_id
         WHERE p.geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
      ORDER BY value DESC NULLS LAST, s.cell_id
         LIMIT :limit
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def pois_geojson(viewport: Viewport, categories: list[str], limit: int = 2000) -> list[dict]:
    """Individual POI points inside the viewport, for the map's marker layer.

    These are the same POIs the grid's poi_* columns count, so a marker layer
    and the activity number beside it always describe the same features.

    Truncation is round-robin across categories rather than sequential. Ordering
    by category and cutting at the limit would fill a busy viewport entirely
    with parking and school, the two largest categories, and show no malls at
    all -- a map that is not just incomplete but misleading about what is there.
    Taking the nth of every category in turn keeps the cut proportional until
    the small categories run out.
    """
    sql = """
        WITH inside AS (
            SELECT id, osm_id, category, name, cell_id, geom
              FROM planning_pois
             WHERE geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
               AND category = ANY(:categories)
        ),
        spread AS (
            SELECT *, row_number() OVER (PARTITION BY category ORDER BY id) AS rn
              FROM inside
        )
        SELECT id, osm_id, category, name, cell_id,
               round(ST_X(geom)::numeric, 6) AS lon,
               round(ST_Y(geom)::numeric, 6) AS lat
          FROM spread
      ORDER BY rn, category
         LIMIT :limit
    """
    params = {"west": viewport.west, "south": viewport.south,
              "east": viewport.east, "north": viewport.north,
              "categories": categories, "limit": limit}
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def pois_clustered(viewport: Viewport, categories: list[str], cell: float,
                   limit: int = 2000) -> list[dict]:
    """POI points grouped on a grid, one feature per occupied cell.

    Used when the viewport holds more points than can be drawn. Each group
    reports its own count, so the numbers on screen still sum to the number in
    the viewport: this aggregates the layer rather than truncating it.

    The marker is placed at the true centroid of its members, not at the grid
    corner, so a cluster sits where its POIs actually are. `mode()` gives the
    dominant category so the client can colour the group by what it mostly is.
    """
    sql = """
        WITH inside AS (
            SELECT geom, category
              FROM planning_pois
             WHERE geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
               AND category = ANY(:categories)
        ),
        grouped AS (
            SELECT ST_SnapToGrid(geom, :cell) AS bucket,
                   count(*) AS n,
                   ST_Centroid(ST_Collect(geom)) AS centre,
                   mode() WITHIN GROUP (ORDER BY category) AS top_category
              FROM inside
          GROUP BY ST_SnapToGrid(geom, :cell)
        )
        SELECT n, top_category,
               round(ST_X(centre)::numeric, 6) AS lon,
               round(ST_Y(centre)::numeric, 6) AS lat
          FROM grouped
      ORDER BY n DESC
         LIMIT :limit
    """
    params = {"west": viewport.west, "south": viewport.south,
              "east": viewport.east, "north": viewport.north,
              "categories": categories, "cell": cell, "limit": limit}
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def supply_fingerprint() -> str:
    """Two counts that say whether the supply half of a suitability score is stale.

    services/resemblance_scale documents why it could not do this: detecting a
    feature reload there would have cost a whole-grid pass on every request. Here
    the probe is two counts over ~1,200 rows, and supply is half the formula
    rather than none of it, so the trade goes the other way.
    """
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT (SELECT count(*) FROM stations) AS s, "
            "       (SELECT count(*) FROM connectors) AS c")).mappings().one()
    return f"{row['s']}/{row['c']}"


def features_for_scoring(feature_names: list[str], min_overlap: float = 0.5,
                         excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Every cell the suitability scale is built over, with its supply columns.

    The whole filtered region, never a viewport and never a circle. Ranking a
    cell inside the circle it was found in makes the best cell of a quiet suburb
    equal to the best cell of Sudirman -- the invariant candidate_sites_in_radius
    spends thirty lines defending, and the reason this is a separate query rather
    than a reuse of the viewport fetchers.

    Built cells are included. They are part of the region a cell is compared
    against even though nothing recommends them.
    """
    with engine.connect() as c:
        known = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'planning_cells'"""))}
        unknown = [f for f in feature_names if f not in known]
        if unknown:
            raise ValueError(
                f"the model expects {len(unknown)} column(s) planning_cells does not "
                f"have: {', '.join(unknown)}. The model is stale relative to the schema.")

        cols = ", ".join(f'"{f}"' for f in feature_names)
        rows = c.execute(text(f"""
            SELECT cell_id, station_count, stations_2km, nearest_station_m, {cols}
              FROM planning_cells
             WHERE overlap_frac >= :min_overlap
               AND kota <> ALL(:excluded_kota)
        """), {"min_overlap": min_overlap,
               "excluded_kota": excluded_kota if excluded_kota is not None
               else DEFAULT_EXCLUDED_KOTA}).mappings().all()
    return [dict(r) for r in rows]


def candidate_cells(feature_names: list[str], min_overlap: float = 0.5,
                    excluded_kota: Optional[list[str]] = None,
                    lat: Optional[float] = None, lon: Optional[float] = None,
                    radius_km: Optional[float] = None) -> list[dict]:
    """Cells a suggestion may be placed on, with everything needed to score one.

    Only cells with no station on them. Unlike features_for_scoring, which pulls
    the whole region because the SCALE has to be built over the whole region,
    this pulls the population a pin may actually land on -- so it carries the
    display columns a candidate is reported with, and it accepts a circle.

    The circle filters the CANDIDATES, never the scale. The regional scale is
    built once and cached; scoring a circle against it is what keeps a cell in
    Serpong and a cell in Sudirman on one comparable number.
    """
    with engine.connect() as c:
        known = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'planning_cells'"""))}
        unknown = [f for f in feature_names if f not in known]
        if unknown:
            raise ValueError(
                f"the model expects {len(unknown)} column(s) planning_cells does not "
                f"have: {', '.join(unknown)}. The model is stale relative to the schema.")

        params: dict = {"min_overlap": min_overlap,
                        "excluded_kota": excluded_kota if excluded_kota is not None
                        else DEFAULT_EXCLUDED_KOTA}
        circle = ""
        if lat is not None and lon is not None and radius_km is not None:
            params.update(lat=lat, lon=lon, radius_m=radius_km * 1000.0,
                          degrees=(radius_km * 1000.0) / 111_320.0)
            # The bounding box first so the GIST index is used, then the exact
            # geography test -- the same two-step every other radius query here
            # does, for the same reason.
            circle = """
               AND centroid && ST_Expand(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :degrees)
               AND ST_DWithin(centroid::geography,
                              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)"""

        cols = ", ".join(f'"{f}"' for f in feature_names)
        rows = c.execute(text(f"""
            SELECT cell_id, kota, station_count, stations_2km, nearest_station_m,
                   ST_Y(centroid) AS latitude, ST_X(centroid) AS longitude,
                   population, poi_total, {cols}
              FROM planning_cells
             WHERE overlap_frac >= :min_overlap
               AND kota <> ALL(:excluded_kota)
               AND station_count = 0{circle}
        """), params).mappings().all()
    return [dict(r) for r in rows]


def landuse_in_viewport(viewport: Viewport, classes: Optional[list[str]] = None,
                        limit: int = 4000, simplify_m: float = 0.0) -> tuple[list[dict], int]:
    """Land-use polygons inside the viewport, and the true total before the limit.

    THIS IS THE SHAPE, NOT THE SHARE

    planning_cells carries lu_*_share: how much of a 500 m cell each class
    covers. That is a model feature and a poor map -- a city block and the road
    beside it come out the same colour. These are the polygons those shares were
    measured from, so what is drawn and what is scored describe the same land.

    Classes do not overlap: every square metre belongs to exactly one, resolved
    by priority upstream. So drawing order cannot change what a planner sees,
    which is the difference between a legend that can be trusted and one that
    happens to be right at the current zoom.

    WHY simplify_m EXISTS AND WHY IT DEFAULTS TO OFF

    Zoomed out, these are tens of thousands of polygons whose vertices are finer
    than a screen pixel, and the response, not the query, is the cost. The caller
    passes a tolerance matched to its zoom. It defaults to 0 because a wrong
    tolerance silently deforms boundaries, and a caller that has not thought
    about zoom should get the truth rather than a guess.

    The count is taken before the limit for the same reason cells_geojson does
    it: a client that cannot tell a complete layer from a cut one will present a
    partial map as the whole picture.
    """
    where = ["geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)"]
    params = {"west": viewport.west, "south": viewport.south,
              "east": viewport.east, "north": viewport.north, "limit": limit}
    if classes:
        where.append("landuse = ANY(:classes)")
        params["classes"] = classes
    clause = " AND ".join(where)

    # ST_Simplify can collapse a sliver to an empty or non-polygonal geometry, so
    # the result is filtered rather than emitted as a null feature the client has
    # to defend against.
    geom_expr = ("ST_Simplify(geom, :tolerance)" if simplify_m > 0 else "geom")
    if simplify_m > 0:
        params["tolerance"] = simplify_m

    with engine.connect() as c:
        total = c.execute(text(f"SELECT count(*) FROM planning_landuse WHERE {clause}"),
                          {k: v for k, v in params.items() if k != "limit"}).scalar()
        rows = c.execute(text(f"""
            SELECT landuse,
                   ST_AsGeoJSON({geom_expr}) AS geojson,
                   ST_Area(geom::geography)  AS area_m2
              FROM planning_landuse
             WHERE {clause}
               AND NOT ST_IsEmpty({geom_expr})
             -- Biggest first, so a truncated layer loses slivers rather than
             -- whichever rows the planner happened to insert last.
             ORDER BY ST_Area(geom) DESC
             LIMIT :limit
        """), params).mappings().all()
    return [dict(r) for r in rows], int(total or 0)


def pois_in_viewport(viewport: Viewport, categories: list[str]) -> dict:
    """Per-category totals before the row limit, so a cut layer can say so."""
    sql = """
        SELECT category, count(*) AS n
          FROM planning_pois
         WHERE geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
           AND category = ANY(:categories)
      GROUP BY category
    """
    params = {"west": viewport.west, "south": viewport.south,
              "east": viewport.east, "north": viewport.north,
              "categories": categories}
    with engine.connect() as c:
        return {r["category"]: r["n"] for r in c.execute(text(sql), params).mappings()}


def cells_in_viewport(viewport: Viewport, min_overlap: float = 0.5,
                      excluded_kota: Optional[list[str]] = None) -> int:
    """How many cells the viewport actually covers, so a truncated response can say so."""
    sql = """
        SELECT count(*) FROM planning_cells
         WHERE overlap_frac >= :min_overlap
           AND kota <> ALL(:excluded_kota)
           AND geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
    """
    with engine.connect() as c:
        return c.execute(text(sql), {
            "west": viewport.west, "south": viewport.south,
            "east": viewport.east, "north": viewport.north,
            "min_overlap": min_overlap,
            "excluded_kota": excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA,
        }).scalar_one()


def get_cell(cell_id: str, weights: Optional[SiteWeights] = None,
             min_overlap: float = 0.5,
             excluded_kota: Optional[list[str]] = None) -> Optional[dict]:
    """Every feature for one cell, plus its score and rank under the weights.

    The filter defaults match score_cells deliberately. A percentile rank is a
    position within a set, so ranking one cell against all 28,176 while the map
    ranks it against the 27,219 that survive the filter gives the same cell two
    different scores, and a planner who clicks a cell scored 0.8390 on the map
    would read 0.8374 in the panel.

    A cell outside the filter is still returned, because it is still on the map
    and clicking it should explain itself rather than 404. It comes back with a
    null score and `in_scored_set` false, which says "not ranked" instead of
    quietly ranking it on a different basis.
    """
    params = _weight_params(weights or SiteWeights())
    params.update(cell_id=cell_id, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    # Built from POI_CATEGORIES rather than typed out. The hand-written list
    # stopped at the original seventeen, so every dwell category migration 0022
    # added -- hotel, cafe, supermarket, thirteen in all -- was missing from this
    # response while sitting in the table and in every other endpoint.
    poi_columns = ", ".join(f"p.poi_{c}" for c in POI_CATEGORIES)
    sql = _RANKED + f""",
    with_rank AS (
        SELECT cell_id, score, rank() OVER (ORDER BY score DESC) AS rank_overall
          FROM scored
    )
        SELECT p.cell_id, p.kota, w.score, w.rank_overall,
               (SELECT count(*) FROM scored) AS cells_total,
               (w.cell_id IS NOT NULL) AS in_scored_set,
               ST_Y(p.centroid) AS latitude, ST_X(p.centroid) AS longitude,
               p.overlap_frac, p.population,
               {poi_columns}, p.poi_total,
               p.lu_commercial_share, p.lu_retail_share,
               p.lu_residential_share, p.lu_industrial_share,
               p.road_nodes, p.road_length_m,
               p.station_count, p.connector_count,
               round(p.nearest_station_m::numeric, 0) AS nearest_station_m, p.stations_2km
          FROM planning_cells p
     LEFT JOIN with_rank w ON w.cell_id = p.cell_id
         WHERE p.cell_id = :cell_id
    """
    with engine.connect() as c:
        row = c.execute(text(sql), params).mappings().first()
    return dict(row) if row else None


def save_site(user_id: str, cell_id: str) -> None:
    """Idempotently bookmark a real planning cell for one planner."""
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO planner_saved_sites (user_id, cell_id)
            VALUES (:user_id, :cell_id)
            ON CONFLICT (user_id, cell_id) DO NOTHING
        """), {"user_id": user_id, "cell_id": cell_id})


def unsave_site(user_id: str, cell_id: str) -> None:
    """Idempotently remove only this planner's bookmark."""
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM planner_saved_sites
            WHERE user_id = :user_id AND cell_id = :cell_id
        """), {"user_id": user_id, "cell_id": cell_id})


def is_site_saved(user_id: str, cell_id: str) -> bool:
    with engine.connect() as c:
        return bool(c.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM planner_saved_sites
                WHERE user_id = :user_id AND cell_id = :cell_id
            )
        """), {"user_id": user_id, "cell_id": cell_id}).scalar_one())


def list_saved_sites(user_id: str) -> list[dict]:
    """Return current planning values, newest bookmark first with a stable tie-break."""
    params = _weight_params(SiteWeights())
    params.update(user_id=user_id, min_overlap=0.5, excluded_kota=DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """
        SELECT pss.cell_id, p.kota,
               ST_Y(p.centroid) AS latitude,
               ST_X(p.centroid) AS longitude,
               s.score, p.poi_total,
               round(p.nearest_station_m::numeric, 0) AS nearest_station_m,
               p.road_nodes, p.lu_residential_share, pss.saved_at
          FROM planner_saved_sites pss
          JOIN planning_cells p ON p.cell_id = pss.cell_id
     LEFT JOIN scored s ON s.cell_id = pss.cell_id
         WHERE pss.user_id = :user_id
      ORDER BY pss.saved_at DESC, pss.cell_id ASC
    """
    with engine.connect() as c:
        return [dict(row) for row in c.execute(text(sql), params).mappings().all()]


def nearby_stations(cell_id: str, radius_km: float = 5.0, limit: int = 10) -> list[dict]:
    """Existing stations around a cell, nearest first (Epic 5 benchmarking)."""
    sql = """
        SELECT s.id, s.name, s.operator, s.power_kw, s.speed_tier,
               ST_Y(s.geom) AS latitude, ST_X(s.geom) AS longitude,
               round(ST_Distance(p.centroid::geography, s.geom::geography)::numeric, 0) AS distance_m,
               count(c.id) FILTER (WHERE c.status = 'available') AS available_connectors,
               count(c.id) AS total_connectors
          FROM planning_cells p
          JOIN stations s
            ON ST_DWithin(p.centroid::geography, s.geom::geography, :radius_m)
     LEFT JOIN connectors c ON c.station_id = s.id
         WHERE p.cell_id = :cell_id
      GROUP BY s.id, s.name, s.operator, s.power_kw, s.speed_tier, p.centroid, s.geom
      ORDER BY distance_m
         LIMIT :limit
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {"cell_id": cell_id, "radius_m": radius_km * 1000.0,
                                     "limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def grid_summary() -> dict:
    """Coverage of the loaded grid, for a health check and for the dashboard header."""
    sql = """
        SELECT count(*)                                        AS cells,
               count(*) FILTER (WHERE station_count > 0)        AS cells_with_station,
               count(*) FILTER (WHERE population > 0)           AS cells_populated,
               COALESCE(sum(station_count), 0)                  AS stations,
               COALESCE(sum(connector_count), 0)                AS connectors,
               COALESCE(round(sum(population)::numeric, 0), 0)  AS population_total,
               count(DISTINCT kota)                             AS areas,
               max(built_at)                                    AS built_at
          FROM planning_cells
    """
    with engine.connect() as c:
        return dict(c.execute(text(sql)).mappings().one())
