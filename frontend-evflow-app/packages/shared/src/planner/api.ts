import { getAuthHeaders } from '../auth/session';
import { EVFLOW_API_BASE_URL } from '../stations/api';

export type PlannerWeights = {
  coverage: number;
  population: number;
  activity: number;
  roads: number;
};

export const defaultPlannerWeights: PlannerWeights = {
  coverage: 0.35,
  population: 0.35,
  activity: 0.2,
  roads: 0.1
};

export type PlannerProvenance = {
  population_source: string;
  features_source: string;
  demand_basis: string;
  cell_size_m: number;
};

export type PlannerCandidateApi = {
  cluster_id: number;
  cell_id: string;
  kota: string | null;
  score: number;
  latitude: number;
  longitude: number;
  population: number;
  poi_total: number;
  station_count: number;
  nearest_station_m: number | null;
  stations_2km: number;
  cluster_size: number;
  /** Present only under basis 'suitability'. `score` is then the suitability. */
  suitability_band?: string | null;
  sessions_per_connector_day?: number | null;
  supply_discount?: number | null;
};

export type PlannerCandidatesResponse = {
  weights_applied: Record<string, number>;
  candidates: PlannerCandidateApi[];
  /**
   * Which number ranked these.
   *
   * Read it rather than assuming what was asked for: a request for
   * 'suitability' answers 'weighted' when the model is unavailable, because a
   * planner asking for suggestions is better served by the weighted score than
   * by a 503.
   */
  basis: 'weighted' | 'suitability';
  excluded_areas: string[];
  provenance: PlannerProvenance;
};

export type PlannerSavedSiteApi = {
  cell_id: string;
  kota: string | null;
  latitude: number;
  longitude: number;
  score: number | null;
  poi_total: number;
  nearest_station_m: number | null;
  road_nodes: number;
  lu_residential_share: number;
  saved_at: string;
};

export type PlannerSavedSiteStatusApi = { cell_id: string; saved: boolean };
export type PlannerSavedSitesResponse = { items: PlannerSavedSiteApi[]; total: number };

export type PlannerCellProperties = {
  cell_id: string;
  kota: string | null;
  value: number | null;
  score: number | null;
  population: number;
  poi_total: number;
  station_count: number;
  nearest_station_m: number | null;
};

export type PlannerGeoJsonGeometry = {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: number[][][] | number[][][][];
};

export type PlannerCellsGeoJsonResponse = {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: PlannerGeoJsonGeometry;
    properties: PlannerCellProperties;
  }>;
  metric: string;
  weights_applied: Record<string, number>;
  cells_returned: number;
  cells_in_viewport: number;
  truncated: boolean;
  provenance: PlannerProvenance;
};

export type PlannerCellDetailApi = {
  cell_id: string;
  kota: string | null;
  latitude: number;
  longitude: number;
  score: number | null;
  rank_overall: number | null;
  cells_total: number;
  in_scored_set: boolean;
  overlap_frac: number | null;
  population: number;
  poi: Record<string, number>;
  land_use: Record<string, number>;
  road_nodes: number;
  road_length_m: number;
  station_count: number;
  connector_count: number;
  nearest_station_m: number | null;
  stations_2km: number;
  /**
   * The same number the heatmap paints this cell with.
   *
   * This is what lets the feasibility card say "Located in a Red Demand Zone"
   * and have it be the colour under the cursor, rather than a second expression
   * that agrees by inspection. Absent when no scale could be built.
   */
  suitability?: number | null;
  suitability_band?: string | null;
  sessions_per_connector_day?: number | null;
  supply_discount?: number | null;
  suitability_scale?: PlannerSuitabilityScaleApi | null;
  provenance: PlannerProvenance;
};

export type PlannerNearbyStationApi = {
  id: string;
  latitude: number;
  longitude: number;
  name: string | null;
  operator: string | null;
  power_kw: number | null;
  speed_tier: string | null;
  distance_m: number;
  available_connectors: number;
  total_connectors: number;
};

export type PlannerBenchmarkResponse = {
  cell_id: string;
  radius_km: number;
  stations: PlannerNearbyStationApi[];
  provenance: PlannerProvenance;
};

export type PlannerRoiInput = {
  cell_id: string;
  capex_per_connector_idr: number;
  opex_monthly_idr: number;
  sessions_per_day?: number;
  utilisation_target?: number;
  connectors?: number;
  power_kw?: number;
  energy_per_session_kwh?: number;
  tariff_idr_per_kwh?: number;
  admin_fee_idr?: number;
  energy_cost_idr_per_kwh?: number;
  horizon_years?: number;
};

export type PlannerRoiResolvedInputs = {
  connectors: number;
  power_kw: number;
  sessions_per_day: number;
  energy_per_session_kwh: number;
  capex_per_connector_idr: number;
  opex_monthly_idr: number;
  tariff_idr_per_kwh: number;
  admin_fee_idr: number;
  energy_cost_idr_per_kwh: number;
  horizon_years: number;
};

export type PlannerRoiResponse = {
  cell_id: string;
  kota: string | null;
  score: number | null;
  population: number;
  poi_total: number;
  station_count: number;
  nearest_station_m: number | null;
  stations_2km: number;
  sessions_per_day: number;
  sessions_per_month: number;
  energy_per_month_kwh: number;
  capacity_sessions_per_day: number;
  utilisation: number;
  revenue_monthly_idr: number;
  energy_cost_idr_per_kwh: number;
  energy_cost_monthly_idr: number;
  opex_monthly_idr: number;
  gross_margin_monthly_idr: number;
  capex_total_idr: number;
  payback_months: number | null;
  payback_years: number | null;
  net_at_horizon_idr: number;
  breaks_even: boolean;
  horizon_years: number;
  inputs: PlannerRoiResolvedInputs;
  input_sources: Record<string, string>;
  demand_basis: string;
  cost_basis: string;
  provenance: PlannerProvenance;
};

export type PlannerViewportRequest = {
  west: number;
  south: number;
  east: number;
  north: number;
  metric?: string;
  limit?: number;
  weights?: PlannerWeights;
  signal?: AbortSignal;
};

export class PlannerApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'PlannerApiError';
    this.status = status;
  }
}

/**
 * Suggested sites, either across the region or within a radius of a point.
 *
 * Pass `centre` and the search becomes "what is good around here": the quantile
 * gate is dropped, because inside a 3 km circle it usually leaves nothing and an
 * empty list reads as "no candidates" rather than "none of these cleared a bar
 * you were never shown".
 *
 * `score` stays comparable between places either way, because the ranks behind
 * it are computed over the whole region before the circle is applied. Measured
 * on four 3 km circles it does separate them: Sudirman 0.673, Cibubur 0.722,
 * Serpong 0.730, south Bogor 0.729.
 *
 * There is deliberately no percentile in the response. An earlier version had
 * one, and on those same four circles the best cell came out at the 0.953,
 * 0.991, 0.993 and 0.993 percentile: take 115 cells from 27,219 and the maximum
 * lands in the top percentile almost every time, so it labelled everywhere a
 * planner clicked as regionally top-tier.
 */
export async function fetchPlannerCandidates(
  options: {
    clusters?: number; quantile?: number; weights?: PlannerWeights;
    /**
     * Which number ranks the suggestions. Omitted means the API's own default,
     * which is the weighted score.
     *
     * Always read `basis` on the response rather than assuming this was
     * honoured: a request for 'suitability' answers 'weighted' when no model is
     * loaded, because suggestions from the weighted score beat a 503.
     */
    basis?: 'weighted' | 'suitability';
    centre?: { latitude: number; longitude: number; radiusKm: number };
    signal?: AbortSignal;
  } = {},
  fetcher: typeof fetch = fetch
) {
  const query = new URLSearchParams({
    clusters: String(options.clusters ?? (options.centre ? 8 : 15)),
    quantile: String(options.quantile ?? 0.9)
  });
  if (options.basis) query.set('basis', options.basis);
  if (options.centre) {
    query.set('lat', String(options.centre.latitude));
    query.set('lon', String(options.centre.longitude));
    query.set('radius_km', String(options.centre.radiusKm));
  }
  return plannerRequest<PlannerCandidatesResponse>(`/api/v1/planner/candidates?${query}`, {
    body: JSON.stringify(options.weights ?? defaultPlannerWeights),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
    signal: options.signal
  }, fetcher);
}

export async function fetchPlannerCells(request: PlannerViewportRequest, fetcher: typeof fetch = fetch) {
  const weights = request.weights ?? defaultPlannerWeights;
  const query = new URLSearchParams({
    bbox: [request.west, request.south, request.east, request.north].join(','),
    metric: request.metric ?? 'score',
    limit: String(request.limit ?? 10_000),
    coverage: String(weights.coverage),
    population: String(weights.population),
    activity: String(weights.activity),
    roads: String(weights.roads)
  });
  return plannerRequest<PlannerCellsGeoJsonResponse>(`/api/v1/planner/cells.geojson?${query}`, {
    signal: request.signal
  }, fetcher);
}

export function fetchPlannerCell(cellId: string, fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerCellDetailApi>(`/api/v1/planner/cells/${encodeURIComponent(cellId)}`, {}, fetcher);
}

export function fetchPlannerBenchmark(cellId: string, radiusKm = 5, fetcher: typeof fetch = fetch, limit = 10) {
  const query = new URLSearchParams({ radius_km: String(radiusKm), limit: String(limit) });
  return plannerRequest<PlannerBenchmarkResponse>(
    `/api/v1/planner/benchmark/${encodeURIComponent(cellId)}?${query}`,
    {},
    fetcher
  );
}

export function fetchPlannerRoi(input: PlannerRoiInput, fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerRoiResponse>('/api/v1/planner/roi', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  }, fetcher);
}

export function fetchPlannerSavedSites(fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerSavedSitesResponse>('/api/v1/planner/saved-sites', {}, fetcher);
}

export function fetchPlannerSavedSiteStatus(cellId: string, fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerSavedSiteStatusApi>(`/api/v1/planner/saved-sites/${encodeURIComponent(cellId)}`, {}, fetcher);
}

export function savePlannerSite(cellId: string, fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerSavedSiteStatusApi>(`/api/v1/planner/saved-sites/${encodeURIComponent(cellId)}`, { method: 'PUT' }, fetcher);
}

export function deletePlannerSavedSite(cellId: string, fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerSavedSiteStatusApi>(`/api/v1/planner/saved-sites/${encodeURIComponent(cellId)}`, { method: 'DELETE' }, fetcher);
}

export type PlannerModelInfoApi = {
  trained_at: string;
  n_samples: number;
  n_positive: number;
  /** Leave-one-area-out AUC. The honest figure: it holds out a whole kota. */
  loco_auc: number;
  /** Inflated. Neighbouring cells fall on both sides of a random split. */
  random_split_auc: number;
  label: string;
  sklearn_version: string;
  n_features: number;
};

/**
 * Provenance for the PRESCRIPTIVE model, which answers a different question
 * from PlannerModelInfoApi above.
 *
 * That one scores how much a cell resembles the ones that already hold a
 * station, and its 500 highest cells are 100% cells that already do — so it
 * cannot rank a place nobody has built on. This one predicts how busy a
 * connector at a place would be, and can.
 *
 * It is a SCENARIO, not a forecast. Every session it learned from is simulation
 * output, and that simulation distributes demand by a formula we wrote:
 * 0.53·rank(population) + 0.30·rank(poi_total) + 0.17·rank(road_nodes). The
 * model recovers that assumption. Show the caveat wherever the number appears.
 */
export type PlannerUtilisationInfoApi = {
  trained_at: string;
  n_samples: number;
  /**
   * Leave-one-area-out R2 on the training target, hardware variation included.
   *
   * NOT a measure of place-ranking skill: 57% of the model's importance is
   * charger power, which is held constant when cells are compared. What speaks
   * to ranking is the spread across the grid, 1.66x against the simulation's
   * own 1.64x.
   */
  loco_r2: number;
  random_split_r2: number;
  label: string;
  target_units: string;
  sklearn_version: string;
  n_features: number;
  /**
   * The hardware every cell is scored at, so what differs between cells is
   * location and nothing else. Sessions per connector depend heavily on charger
   * power; comparing cells at different specs compares the chargers.
   */
  reference_spec: Record<string, number>;
  window_start: string;
  window_end: string;
  /** Complete local days of demand-weighted simulation behind the fit. */
  window_days: number;
  /**
   * Measured ratio of sessions per connector between the top and bottom
   * demand-factor quartile. The evidence that the weighting reached the sessions
   * the model learned from; around 1.0 would mean it did not.
   */
  dose_response: number;
  counting_noise_pct: number | null;
};

export type PlannerPredictionApi = {
  cell_id: string;
  kota: string | null;
  probability: number;
  /**
   * Whether this cell ALREADY has a station.
   *
   * Not decoration. Measured across all 27,219 cells, the model's 500
   * highest-probability cells are 100% cells that already have one, so a view
   * that ignores this flag ranks existing sites as candidates.
   */
  has_station: boolean;
  /**
   * Prescriptive model: simulated sessions a connector here would turn over per
   * day, at the reference spec in PlannerUtilisationInfoApi.
   *
   * Null when no utilisation artifact is loaded. A client that gets null must
   * say so rather than fall back to `probability`, which answers a different
   * question.
   */
  sessions_per_connector_day: number | null;
  /**
   * The number the heatmap paints: the model's demand ranking blended with a
   * discount for what is already built nearby, both ranked over the whole
   * region. 0..1.
   *
   * Null when no scale could be built. A client that gets null must OMIT the
   * band rather than assume green — green means "already well served", which is
   * the opposite of "we do not know".
   */
  suitability: number | null;
  /** 'red' | 'yellow' | 'green', against the floors in suitability_scale. */
  suitability_band: string | null;
  /** 1/(1 + effective stations within 2 km). 1.0 means nothing nearby. */
  supply_discount: number | null;
  /** Stations within 2 km. Stations, not connectors — see the API docstring. */
  stations_2km: number | null;
};

/**
 * The regional distribution a band was decided against.
 *
 * Returned with the cells rather than hardcoded so the legend prints the same
 * numbers the shading used. A retrain or a station import moves these floors,
 * and a client holding constants would band cells against a distribution that
 * no longer exists.
 */
export type PlannerSuitabilityScaleApi = {
  red_floor: number;
  yellow_floor: number;
  cells_scored: number;
  /** How much of the blend is the model. 0.5 today; read it, do not assume it. */
  model_weight: number;
};

export type PlannerPredictResponse = {
  predictions: PlannerPredictionApi[];
  model: PlannerModelInfoApi;
  /** Null when no utilisation artifact is loaded; every prediction's field is null too. */
  utilisation_model: PlannerUtilisationInfoApi | null;
  /** What a high probability does and does not mean. Show it; do not summarise it. */
  interpretation: string;
  provenance: PlannerProvenance;
};

/**
 * How the model's probabilities are spread across the cells in a chosen area.
 *
 * There is deliberately no single area-wide probability. The model was fitted on
 * 500 m cells; summing an area into one feature vector pushes most of its inputs
 * past anything in the training set (18 of 33 features for a 10 x 10 km
 * selection) and a random forest cannot extrapolate there. Measured, that shape
 * answered 0.605 where the true per-cell mean was 0.040. Read the distribution,
 * and if a headline number is needed use `mean_probability` — which is an
 * average of real predictions rather than a prediction about an average.
 */
export type PlannerAreaDistributionApi = {
  /** Cells the area really holds, before any limit. Compare with cells_predicted. */
  cells_in_area: number;
  cells_predicted: number;
  /** True when the area held more cells than the request returned. Say so in the UI. */
  truncated: boolean;
  /** Cells here that already have a station. Context, not candidates. */
  cells_with_station: number;
  /** Cells here with none. The only ones that could be built on. */
  cells_without_station: number;
  /**
   * Resemblance among cells WITHOUT a station. Null when every cell here has one.
   *
   * Do not read these against 0.5. Measured on the full grid, no cell without a
   * station reaches 0.305, so a half-way threshold only ever selected cells that
   * were already built on.
   */
  mean_probability: number | null;
  median_probability: number | null;
  max_probability: number | null;
  /**
   * The highest resemblance ANY unbuilt cell in the region reaches, derived from
   * the loaded model rather than written down here.
   *
   * This was a frontend constant, EMPTY_CELL_CEILING = 0.31. Correct when
   * written, with no way to stay correct: the ceiling depends on the model, and
   * the POI expansion in migration 0022 means the model needs retraining. A
   * retrain would have left the dashboard quoting a percentage of the wrong
   * denominator, silently.
   *
   * Null means it could not be derived. Omit the comparison entirely in that
   * case; do NOT substitute a remembered number.
   */
  resemblance_ceiling: number | null;
  /** How many unbuilt cells the ceiling was taken over, so it is auditable. */
  resemblance_ceiling_cells: number | null;
  /**
   * Predicted sessions per connector per day among cells WITHOUT a station.
   *
   * Unbuilt cells only, for the same reason the resemblance figures are: a
   * summary that mixes in built cells describes the network that exists rather
   * than the opportunity being assessed.
   */
  mean_sessions_per_connector_day: number | null;
  median_sessions_per_connector_day: number | null;
  /**
   * Highest predicted utilisation among unbuilt cells here.
   *
   * Read it against the grid-wide spread of about 1.66x between the 5th and 95th
   * percentile. This model separates places by well under an order of magnitude,
   * and a scale implying more overstates the difference between two cells.
   */
  max_sessions_per_connector_day: number | null;
  /**
   * The floors the bands were cut at, over the whole region.
   *
   * Null when no scale could be built, in which case every prediction's
   * suitability_band is null too and a client must show no band at all.
   */
  suitability_scale: PlannerSuitabilityScaleApi | null;
  /** Band counts among cells WITHOUT a station, here. Null with no scale. */
  cells_red: number | null;
  cells_yellow: number | null;
  cells_green: number | null;
  /**
   * Chargers within 2 km at the typical place here, built places included.
   *
   * This is what makes a one-colour map readable. An area whose typical place
   * already has 25 chargers within 2 km is uniformly green because it IS
   * uniformly covered, and without this figure that is indistinguishable from
   * a scale that has stopped working.
   */
  median_stations_2km: number | null;
};

export type PlannerPredictAreaResponse = {
  distribution: PlannerAreaDistributionApi;
  /**
   * Per-cell predictions, ordered by predicted utilisation, highest first —
   * that is the question a planner asks and the only one of the two models that
   * can answer it for an unbuilt cell. Falls back to resemblance order when no
   * utilisation artifact is loaded. Trimmed by `top`; the distribution is not.
   */
  predictions: PlannerPredictionApi[];
  model: PlannerModelInfoApi;
  /** Provenance for sessions_per_connector_day and for the ordering. */
  utilisation_model: PlannerUtilisationInfoApi | null;
  /** What a high probability does and does not mean. Show it; do not summarise it. */
  interpretation: string;
  provenance: PlannerProvenance;
};

/**
 * The land-use classes the map draws, in the priority order that resolved them.
 *
 * They never overlap: every square metre belongs to exactly one, the most
 * specific that claims it. OSM nests them -- a retail park inside a residential
 * district -- and unresolved, drawing order would decide what a planner sees.
 */
export const PLANNER_LANDUSE_CLASSES = ['retail', 'commercial', 'industrial', 'residential'] as const;
export type PlannerLandUseClass = (typeof PLANNER_LANDUSE_CLASSES)[number];

export type PlannerLandUseFeatureApi = {
  landuse: string;
  /** Polygon geometry as a GeoJSON string, WGS84. Parse once, at the draw site. */
  geojson: string;
  area_m2: number;
};

/**
 * Land-use polygons for a viewport.
 *
 * These are SHAPES, not the lu_*_share columns on planning_cells. The shares say
 * how much of a 500 m square each class covers -- a model feature and a poor
 * map, because a city block and the road beside it come out the same colour.
 * These are the polygons those shares were measured from.
 */
export type PlannerLandUseResponse = {
  features: PlannerLandUseFeatureApi[];
  polygons_returned: number;
  /** Counted BEFORE the limit. Compare with polygons_returned before calling the layer complete. */
  polygons_in_viewport: number;
  truncated: boolean;
  classes: string[];
  /**
   * Why blank ground is blank. Half of Jabodetabek's cells carry no land-use
   * polygon at all, so unmapped and empty look identical on screen. Show this
   * rather than letting a planner read absence as open ground.
   */
  coverage_note: string;
  provenance: PlannerProvenance;
};

/**
 * Land-use polygons inside a viewport.
 *
 * `simplifyM` is a Douglas-Peucker tolerance in degrees, matched to zoom.
 * Zoomed out, polygon vertices are finer than a screen pixel and the response,
 * not the query, is the cost. Zoomed in it must be 0 or boundaries deform.
 */
export function fetchPlannerLandUse(
  request: { west: number; south: number; east: number; north: number;
             classes?: readonly string[]; limit?: number; simplifyM?: number;
             signal?: AbortSignal },
  fetcher: typeof fetch = fetch
) {
  const query = new URLSearchParams({
    bbox: [request.west, request.south, request.east, request.north].join(','),
    limit: String(request.limit ?? 4000)
  });
  if (request.classes?.length) query.set('classes', request.classes.join(','));
  if (request.simplifyM) query.set('simplify_m', String(request.simplifyM));
  return plannerRequest<PlannerLandUseResponse>(
    `/api/v1/planner/landuse.geojson?${query}`, { signal: request.signal }, fetcher);
}

export type PlannerPoiProperties = {
  /** Present in 'points' mode only. */
  id?: number;
  osm_id?: number | null;
  category: string;
  name?: string | null;
  cell_id?: string;
  /** True when this feature is a GROUP of POIs rather than a single place. */
  cluster: boolean;
  /** Present in 'clustered' mode: how many POIs this feature stands for. */
  count?: number;
};

export type PlannerPoisResponse = {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: { type: 'Point'; coordinates: number[] };
    properties: PlannerPoiProperties;
  }>;
  categories: string[];
  /**
   * 'points'    every POI in the viewport, individually.
   * 'clustered' too many to draw, so they are grouped on a grid. Each feature
   *             carries a `count`, and those counts sum to the viewport total —
   *             the layer is aggregated, never truncated. Zoom in to return to
   *             'points'.
   */
  mode: 'points' | 'clustered';
  /** Features in this response. In clustered mode this counts GROUPS, not POIs. */
  pois_returned: number;
  /** Per-category totals BEFORE the row limit. Read this to know what was cut. */
  pois_in_viewport: Record<string, number>;
  truncated: boolean;
  provenance: PlannerProvenance;
};

/**
 * Individual POI points for the marker layer.
 *
 * These are the same features the grid's poi_* counts describe, so a marker and
 * the activity figure beside it never disagree. Coordinates are GeoJSON order,
 * longitude first — Leaflet takes latitude first, so callers must swap.
 */
export function fetchPlannerPois(
  request: { west: number; south: number; east: number; north: number;
             categories?: string[]; limit?: number; signal?: AbortSignal },
  fetcher: typeof fetch = fetch
) {
  const query = new URLSearchParams({
    bbox: [request.west, request.south, request.east, request.north].join(','),
    limit: String(request.limit ?? 2000)
  });
  if (request.categories?.length) query.set('categories', request.categories.join(','));
  return plannerRequest<PlannerPoisResponse>(`/api/v1/planner/pois.geojson?${query}`, {
    signal: request.signal
  }, fetcher);
}

export function fetchPlannerModel(fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerModelInfoApi>('/api/v1/planner/model', {}, fetcher);
}

/**
 * Trained-model probability for specific cells.
 *
 * The response carries `interpretation` because the number alone is misleading:
 * the model learns where stations ARE, on a network that is mostly PLN
 * placements, so a high value means "resembles somewhere PLN builds" rather
 * than "good site". Render that text alongside the number, never instead of it.
 */
export function fetchPlannerPredictions(cellIds: string[], fetcher: typeof fetch = fetch) {
  return plannerRequest<PlannerPredictResponse>('/api/v1/planner/predict', {
    body: JSON.stringify({ cell_ids: cellIds }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST'
  }, fetcher);
}

/**
 * Score the cells within radiusKm of a point the planner picked, at request time.
 *
 * A circle, not the viewport: "analyse around here" is the question a planner
 * asks, and unlike a viewport it does not change when they resize the window,
 * so two locations can be compared.
 *
 * WHAT THIS ANSWERS. The model is descriptive. It learned which cells CONTAIN a
 * station, from a network 87% operated by PLN (1,038 of 1,192), so it
 * answers "how much does this resemble the places that get built on" and NOT
 * "where should a station go". Read `cells_with_station` beside every other
 * figure: measured on real areas, the three highest-scoring cells around
 * Sudirman, Cibubur and Serpong all already had one.
 *
 * `top` bounds the list that comes back, never the summary. The distribution is
 * always computed over every cell scored, and only over the ones without a
 * station. Check `distribution.truncated` before presenting the area as fully
 * covered.
 */
export function fetchPlannerAreaPrediction(
  request: { latitude?: number; longitude?: number; radiusKm?: number;
             /** 'minLon,minLat,maxLon,maxLat'. Give this OR the point, never both. */
             bbox?: string;
             limit?: number; top?: number; signal?: AbortSignal },
  fetcher: typeof fetch = fetch
) {
  // The endpoint takes a circle or a rectangle and refuses both at once with a
  // 422, so the caller's choice is passed through rather than merged. The
  // rectangle is what a viewport-wide layer needs; the circle is what a planner
  // tapping one place needs.
  const query = new URLSearchParams(
    request.bbox
      ? { bbox: request.bbox }
      : {
          lat: String(request.latitude),
          lon: String(request.longitude),
          radius_km: String(request.radiusKm)
        });
  query.set('limit', String(request.limit ?? 4000));
  query.set('top', String(request.top ?? 200));
  return plannerRequest<PlannerPredictAreaResponse>(
    `/api/v1/planner/predict.area?${query}`, { signal: request.signal }, fetcher);
}

async function plannerRequest<T>(path: string, init: RequestInit, fetcher: typeof fetch): Promise<T> {
  const authHeaders = getAuthHeaders();
  if (!authHeaders) throw new PlannerApiError(401, 'Sign in with a Business Planner account to load planning data.');

  const response = await fetcher(`${EVFLOW_API_BASE_URL}${path}`, {
    ...init,
    headers: { ...authHeaders, ...init.headers }
  });
  if (!response.ok) throw new PlannerApiError(response.status, await plannerErrorMessage(response));
  return response.json() as Promise<T>;
}

async function plannerErrorMessage(response: Response) {
  try {
    const payload = await response.clone().json() as { detail?: unknown };
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail
        .map((item) => item && typeof item === 'object' && 'msg' in item ? (item as { msg?: unknown }).msg : null)
        .filter((message): message is string => typeof message === 'string');
      if (messages.length > 0) return messages.join(' ');
    }
  } catch {
    // Use the role-aware fallback below.
  }
  if (response.status === 401) return 'Your session expired. Sign in again to load planning data.';
  if (response.status === 403) return 'This planning data requires a Business Planner account.';
  return `Planner API request failed with status ${response.status}.`;
}
