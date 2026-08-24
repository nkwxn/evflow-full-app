import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));
vi.mock('../auth/session', () => ({ getAuthHeaders: vi.fn() }));

import { getAuthHeaders } from '../auth/session';
import { EVFLOW_API_BASE_URL } from '../stations/api';
import {
  fetchPlannerBenchmark,
  fetchPlannerCandidates,
  fetchPlannerCell,
  fetchPlannerCells,
  fetchPlannerAreaPrediction,
  fetchPlannerRoi,
  fetchPlannerSavedSites,
  fetchPlannerSavedSiteStatus,
  savePlannerSite,
  deletePlannerSavedSite,
  PlannerApiError
} from './api';

const mockedGetAuthHeaders = vi.mocked(getAuthHeaders);
const auth = { Authorization: 'Bearer planner-token' };

function response(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const value = {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body
  };
  return { ...value, clone: () => ({ ...value }) } as unknown as Response;
}

function fetcherReturning(value: Response) {
  return vi.fn().mockResolvedValue(value) as unknown as typeof fetch;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGetAuthHeaders.mockReturnValue(auth);
});

describe('planner API client', () => {
  it('loads candidates with the backend default weights and planner auth', async () => {
    const payload = { candidates: [] };
    const fetcher = fetcherReturning(response(payload));
    await expect(fetchPlannerCandidates({}, fetcher)).resolves.toBe(payload);

    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/planner/candidates?clusters=15&quantile=0.9`);
    expect(options.headers).toMatchObject({ ...auth, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual({ coverage: 0.35, population: 0.35, activity: 0.2, roads: 0.1 });
  });

  it('serializes the Leaflet viewport in backend bbox order', async () => {
    const fetcher = fetcherReturning(response({ features: [] }));
    await fetchPlannerCells({ west: 106.6, south: -6.4, east: 107, north: -6, metric: 'score' }, fetcher);
    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe('/api/v1/planner/cells.geojson');
    expect(parsed.searchParams.get('bbox')).toBe('106.6,-6.4,107,-6');
    expect(parsed.searchParams.get('limit')).toBe('10000');
    expect(options.headers).toMatchObject(auth);
  });

  it('encodes cell IDs for detail and benchmark requests', async () => {
    const fetcher = fetcherReturning(response({}));
    await fetchPlannerCell('cell / one', fetcher);
    await fetchPlannerBenchmark('cell / one', 5, fetcher);
    const calls = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][0]).toContain('/cells/cell%20%2F%20one');
    expect(calls[1][0]).toContain('/benchmark/cell%20%2F%20one?radius_km=5&limit=10');
  });

  it('fails before fetch when no planner session exists', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = fetcherReturning(response({}));
    await expect(fetchPlannerCandidates({}, fetcher)).rejects.toMatchObject({ status: 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('preserves backend role errors', async () => {
    const fetcher = fetcherReturning(response({ detail: 'this endpoint requires a planner account' }, { ok: false, status: 403 }));
    await expect(fetchPlannerCandidates({}, fetcher)).rejects.toEqual(
      new PlannerApiError(403, 'this endpoint requires a planner account')
    );
  });

  it('posts a typed ROI request with planner auth and JSON content', async () => {
    const payload = {
      cell_id: 'JBDTBK_22219', payback_years: null, breaks_even: false,
      input_sources: { capex_per_connector_idr: 'planner' }
    };
    const fetcher = fetcherReturning(response(payload));
    const input = {
      cell_id: 'JBDTBK_22219', capex_per_connector_idr: 250_000_000,
      opex_monthly_idr: 15_000_000, utilisation_target: 0.2
    };

    await expect(fetchPlannerRoi(input, fetcher)).resolves.toBe(payload);
    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${EVFLOW_API_BASE_URL}/api/v1/planner/roi`);
    expect(options.method).toBe('POST');
    expect(options.headers).toMatchObject({ ...auth, 'Content-Type': 'application/json' });
    expect(JSON.parse(options.body)).toEqual(input);
  });

  it('uses explicit retry-safe methods for saved sites', async () => {
    const fetcher = fetcherReturning(response({ cell_id: 'cell / one', saved: true }));
    await fetchPlannerSavedSites(fetcher);
    await fetchPlannerSavedSiteStatus('cell / one', fetcher);
    await savePlannerSite('cell / one', fetcher);
    await deletePlannerSavedSite('cell / one', fetcher);
    const calls = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][0]).toBe(`${EVFLOW_API_BASE_URL}/api/v1/planner/saved-sites`);
    expect(calls[1][0]).toContain('/saved-sites/cell%20%2F%20one');
    expect(calls[2][1].method).toBe('PUT');
    expect(calls[3][1].method).toBe('DELETE');
    expect(calls.every((call) => call[1].headers.Authorization === auth.Authorization)).toBe(true);
  });

  it.each([
    [401, 'missing bearer token'],
    [403, 'this endpoint requires a planner account'],
    [422, 'assumed demand exceeds hardware capacity']
  ])('preserves ROI error %s detail', async (status, detail) => {
    const fetcher = fetcherReturning(response({ detail }, { ok: false, status }));
    await expect(fetchPlannerRoi({
      cell_id: 'cell', capex_per_connector_idr: 1,
      opex_monthly_idr: 1, utilisation_target: 0.2
    }, fetcher)).rejects.toEqual(new PlannerApiError(status, detail));
  });

  it('surfaces Pydantic validation detail for an invalid ROI demand basis', async () => {
    const fetcher = fetcherReturning(response({
      detail: [{ type: 'value_error', loc: ['body'], msg: 'supply exactly one demand input' }]
    }, { ok: false, status: 422 }));

    await expect(fetchPlannerRoi({
      cell_id: 'cell', capex_per_connector_idr: 1,
      opex_monthly_idr: 1, utilisation_target: 0.2
    }, fetcher)).rejects.toEqual(new PlannerApiError(422, 'supply exactly one demand input'));
  });
});

describe('on-demand area prediction', () => {
  const body = {
    distribution: {
      cells_in_area: 136, cells_predicted: 136, truncated: false,
      cells_with_station: 75, cells_without_station: 61,
      mean_probability: 0.08, median_probability: 0.05, max_probability: 0.26
    },
    predictions: [{ cell_id: 'JBDTBK_19690', kota: 'Kota Jakarta Selatan', probability: 0.97, has_station: true }],
    model: { loco_auc: 0.814 },
    interpretation: 'resembles somewhere PLN builds',
    provenance: {}
  };

  it('sends the chosen point and radius, not a viewport', async () => {
    // A viewport moves when the planner resizes the window, so two places could
    // never be compared. A circle around a chosen point does not.
    const fetcher = fetcherReturning(response(body));
    await fetchPlannerAreaPrediction({ latitude: -6.2088, longitude: 106.8206, radiusKm: 3 }, fetcher);
    const [url, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe('/api/v1/planner/predict.area');
    expect(parsed.searchParams.get('lat')).toBe('-6.2088');
    expect(parsed.searchParams.get('lon')).toBe('106.8206');
    expect(parsed.searchParams.get('radius_km')).toBe('3');
    expect(parsed.searchParams.get('bbox')).toBeNull();
    expect(options.headers).toMatchObject(auth);
  });

  it('is a GET, because a place is a question and not a submission', async () => {
    const fetcher = fetcherReturning(response(body));
    await fetchPlannerAreaPrediction({ latitude: 1, longitude: 2, radiusKm: 1 }, fetcher);
    const [, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(options.method).toBeUndefined();
    expect(options.body).toBeUndefined();
  });

  it('carries the built/unbuilt split, which is what the circle is read by', async () => {
    // A lone area-wide probability would be extrapolated, and a count of cells
    // above 0.5 would be counting existing stations.
    const fetcher = fetcherReturning(response(body));
    const out = await fetchPlannerAreaPrediction({ latitude: 1, longitude: 2, radiusKm: 1 }, fetcher);
    expect(out.distribution.cells_with_station).toBe(75);
    expect(out.distribution.cells_without_station).toBe(61);
    expect(out.predictions[0]?.has_station).toBe(true);
    expect(out).not.toHaveProperty('probability');
    expect(out.distribution).not.toHaveProperty('cells_above_half');
  });

  it('defaults limit and top rather than leaving the backend to guess', async () => {
    const fetcher = fetcherReturning(response(body));
    await fetchPlannerAreaPrediction({ latitude: 1, longitude: 2, radiusKm: 1 }, fetcher);
    const parsed = new URL((fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(parsed.searchParams.get('limit')).toBe('4000');
    expect(parsed.searchParams.get('top')).toBe('200');
  });

  it('needs a planner session before it reaches the network', async () => {
    mockedGetAuthHeaders.mockReturnValue(null);
    const fetcher = fetcherReturning(response(body));
    await expect(fetchPlannerAreaPrediction({ latitude: 1, longitude: 2, radiusKm: 1 }, fetcher))
      .rejects.toMatchObject({ status: 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('candidates within a radius', () => {
  const body = { weights_applied: {}, candidates: [], excluded_areas: [] };

  it('sends the point and radius, and asks for fewer clusters than region-wide', async () => {
    // Fifteen suggestions inside 3 km would be one every 400 m, which is the
    // grid resolution: every cell would become its own suggestion.
    const fetcher = fetcherReturning(response(body));
    await fetchPlannerCandidates(
      { centre: { latitude: -6.2088, longitude: 106.8206, radiusKm: 3 } }, fetcher);
    const parsed = new URL((fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(parsed.searchParams.get('lat')).toBe('-6.2088');
    expect(parsed.searchParams.get('lon')).toBe('106.8206');
    expect(parsed.searchParams.get('radius_km')).toBe('3');
    expect(parsed.searchParams.get('clusters')).toBe('8');
  });

  it('still supports the region-wide search, with no point and fifteen clusters', async () => {
    // Not removed: "the best places anywhere" is a real question, it was just
    // the wrong thing to open the dashboard with.
    const fetcher = fetcherReturning(response(body));
    await fetchPlannerCandidates({}, fetcher);
    const parsed = new URL((fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]);
    expect(parsed.searchParams.get('lat')).toBeNull();
    expect(parsed.searchParams.get('clusters')).toBe('15');
  });

  it('sends the weights as the body either way', async () => {
    const fetcher = fetcherReturning(response(body));
    await fetchPlannerCandidates(
      { centre: { latitude: 1, longitude: 2, radiusKm: 1 } }, fetcher);
    const [, options] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(options.body)).toEqual(
      { coverage: 0.35, population: 0.35, activity: 0.2, roads: 0.1 });
  });
});
