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
};

export type PlannerCandidatesResponse = {
  weights_applied: Record<string, number>;
  candidates: PlannerCandidateApi[];
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
    centre?: { latitude: number; longitude: number; radiusKm: number };
    signal?: AbortSignal;
  } = {},
  fetcher: typeof fetch = fetch
) {
  const query = new URLSearchParams({
    clusters: String(options.clusters ?? (options.centre ? 8 : 15)),
    quantile: String(options.quantile ?? 0.9)
  });
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
};

export type PlannerPredictResponse = {
  predictions: PlannerPredictionApi[];
  model: PlannerModelInfoApi;
  /** What a high probability does and does not mean. Show it; do not summarise it. */
  interpretation: string;
  provenance: PlannerProvenance;
};

/**
 * How the model's probabilities are spread across the cells in a chosen area.
 *
 * There is deliberately no single area-wide probability. The model was fitted on
 * 400 m cells; summing an area into one feature vector pushes most of its inputs
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
};

export type PlannerPredictAreaResponse = {
  distribution: PlannerAreaDistributionApi;
  /** Per-cell probabilities, highest first. Trimmed by `top`; the distribution is not. */
  predictions: PlannerPredictionApi[];
  model: PlannerModelInfoApi;
  /** What a high probability does and does not mean. Show it; do not summarise it. */
  interpretation: string;
  provenance: PlannerProvenance;
};

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
 * station, from a network that is 1,080 PLN placements out of 1,236, so it
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
  request: { latitude: number; longitude: number; radiusKm: number;
             limit?: number; top?: number; signal?: AbortSignal },
  fetcher: typeof fetch = fetch
) {
  const query = new URLSearchParams({
    lat: String(request.latitude),
    lon: String(request.longitude),
    radius_km: String(request.radiusKm),
    limit: String(request.limit ?? 4000),
    top: String(request.top ?? 200)
  });
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
