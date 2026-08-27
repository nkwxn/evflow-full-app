import { describe, expect, it } from 'vitest';
import type { PlannerCandidateApi, PlannerCellsGeoJsonResponse, StationApiItem } from '@evflow/shared';
import {
  plannerCandidateToOptimalSite,
  plannerCellsToMetricPolygons,
  landUseColors,
  plannerLandUsePolygons,
  plannerPredictionsToPolygons,
  plannerStationsToMarkers,
} from './plannerApiAdapters';
import {
  BUILT_COLOUR, RESEMBLANCE_BANDS, SUITABILITY_BANDS
} from './site-prediction/areaPrediction';

describe('planner API adapters', () => {
  it('converts normalized candidate scores and real cell IDs without inventing coordinates', () => {
    const candidate: PlannerCandidateApi = {
      cluster_id: 1, cell_id: 'JBDTBK_13989', kota: 'Kota Jakarta Selatan', score: 0.864,
      latitude: -6.22, longitude: 106.81, population: 1000, poi_total: 19,
      station_count: 0, nearest_station_m: 4000, stations_2km: 0, cluster_size: 30
    };
    expect(plannerCandidateToOptimalSite(candidate)).toEqual({
      id: 'JBDTBK_13989', district: 'Jakarta Selatan', score: 86,
      latitude: -6.22, longitude: 106.81
    });
  });

  it('turns positive planner metrics into geographically anchored density polygons', () => {
    const response = metricResponse('cell-1', 25);
    const { polygons, scale } = plannerCellsToMetricPolygons(response, '#123456', 'population');
    const [polygon] = polygons;
    expect(polygon).toMatchObject({
      id: 'population-cell-1-0',
      fillColor: '#123456'
    });
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
    // No per-cell outline: at 400 m across a city viewport those strokes turned
    // the surface into graph paper, and the grid carried no information.
    expect(polygon?.weight).toBe(0);
    // The scale comes back so the legend can print the values at each break.
    expect(scale?.max).toBe(25);
  });

  it('draws land use as its own polygon, in its own class colour', () => {
    // The old layer blended four per-cell SHARES into one tint per 500 m square,
    // so a colour meant "mostly residential, a bit commercial" and no legend
    // could name it. These are polygons of exactly one class, so the colour is
    // the class and nothing else.
    const [polygon] = plannerLandUsePolygons({
      features: [{
        landuse: 'retail',
        geojson: JSON.stringify({
          type: 'Polygon',
          coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]]
        }),
        area_m2: 1234
      }],
      polygons_returned: 1, polygons_in_viewport: 1, truncated: false,
      classes: ['retail'], coverage_note: '', provenance: {} as never
    });
    expect(polygon?.fillColor).toBe(landUseColors.retail);
    // Leaflet wants [lat, lon]; GeoJSON gives [lon, lat]. Swapping these puts
    // Jabodetabek in the Indian Ocean, and the map still renders.
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
  });

  it('drops one unparseable polygon rather than the whole layer', () => {
    const polygons = plannerLandUsePolygons({
      features: [
        { landuse: 'retail', geojson: '{not json', area_m2: 1 },
        { landuse: 'commercial', geojson: JSON.stringify({
          type: 'Polygon',
          coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]]
        }), area_m2: 2 }
      ],
      polygons_returned: 2, polygons_in_viewport: 2, truncated: false,
      classes: ['retail', 'commercial'], coverage_note: '', provenance: {} as never
    });
    expect(polygons).toHaveLength(1);
    expect(polygons[0]?.fillColor).toBe(landUseColors.commercial);
  });

  it('prefixes real station IDs so station taps cannot resolve as optimal sites', () => {
    const station = {
      id: 'station-1', name: 'SPKLU Test', latitude: -6.2, longitude: 106.8
    } as StationApiItem;
    expect(plannerStationsToMarkers([station])[0]).toMatchObject({
      id: 'station:station-1',
      label: 'SPKLU Test',
      type: 'station'
    });
  });
});

function metricResponse(cellId: string, value: number): PlannerCellsGeoJsonResponse {
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]]
      },
      properties: {
        cell_id: cellId, kota: null, value, score: 0.8, population: 1,
        poi_total: 1, station_count: 0, nearest_station_m: null
      }
    }],
    metric: 'score',
    weights_applied: {},
    cells_returned: 1,
    cells_in_viewport: 1,
    truncated: false,
    provenance: {
      population_source: 'mock', features_source: 'mock', demand_basis: 'mock', cell_size_m: 500
    }
  };
}

describe('on-demand prediction polygons', () => {
  // The regional ceiling the API now supplies. Measured at 0.305 across all
  // 26,334 unbuilt cells; the shading is scaled against it.
  const CEILING = 0.30;

  function cells(...ids: string[]): PlannerCellsGeoJsonResponse {
    return {
      features: ids.map((cell_id) => ({
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]] },
        properties: { cell_id, kota: null, value: 0, score: 0, population: 1, poi_total: 1, station_count: 0, nearest_station_m: null }
      }))
    } as PlannerCellsGeoJsonResponse;
  }
  // The suitability scale the API supplies with every response. Real floors,
  // from the 27,219-cell grid.
  const SUIT = { red_floor: 0.83, yellow_floor: 0.64, cells_scored: 27219, model_weight: 0.5 };
  // Both scales, as the layer receives them. `banded` is the normal state;
  // `unbanded` is what any deployment without the utilisation artifact gets.
  const banded = { suitability: SUIT, resemblanceCeiling: CEILING };
  const unbanded = { suitability: null, resemblanceCeiling: CEILING };

  const pred = (cell_id: string, probability: number, has_station = false,
                suitability: number | null = null) =>
    ({ cell_id, kota: null, probability, has_station, sessions_per_connector_day: null,
       suitability, suitability_band: null, supply_discount: null, stations_2km: 0 });

  it('joins probabilities onto the cells they belong to', () => {
    const out = plannerPredictionsToPolygons([pred('b', 0.25)], cells('a', 'b'), unbanded);
    expect(out).toHaveLength(1);
    expect(out[0]?.id).toContain('b');
  });

  it('draws nothing for a cell with no prediction', () => {
    // The list is trimmed by `top`, so an unmatched cell means "not in the top
    // N". Painting it would state a result the request never asked for. It is
    // also what keeps the drawn shape a circle: the geometry request covers the
    // circle's bounding box, and its corners get no prediction.
    expect(plannerPredictionsToPolygons([], cells('a', 'b'), unbanded)).toHaveLength(0);
  });

  it('ignores a prediction whose cell is outside the loaded geometry', () => {
    expect(plannerPredictionsToPolygons([pred('elsewhere', 0.2)], cells('a'), unbanded)).toHaveLength(0);
  });

  it('swaps GeoJSON longitude/latitude into Leaflet order', () => {
    // Getting this backwards puts every cell in the Indian Ocean: obvious on a
    // map, invisible to a test that only counts polygons.
    const [polygon] = plannerPredictionsToPolygons([pred('a', 0.2)], cells('a'), unbanded);
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
  });

  it('grades unbuilt cells by resemblance', () => {
    const [low] = plannerPredictionsToPolygons([pred('a', 0.02)], cells('a'), unbanded);
    const [high] = plannerPredictionsToPolygons([pred('a', 0.30)], cells('a'), unbanded);
    expect(low?.fillColor).not.toBe(high?.fillColor);
    expect(high?.fillOpacity ?? 0).toBeGreaterThan(low?.fillOpacity ?? 0);
  });

  it('paints unbuilt cells in the suitability bands when a scale is supplied', () => {
    const [top] = plannerPredictionsToPolygons([pred('a', 0.02, false, 0.95)], cells('a'), banded);
    const [mid] = plannerPredictionsToPolygons([pred('a', 0.02, false, 0.70)], cells('a'), banded);
    const [low] = plannerPredictionsToPolygons([pred('a', 0.02, false, 0.10)], cells('a'), banded);
    expect([top?.fillColor, mid?.fillColor, low?.fillColor])
      .toEqual(SUITABILITY_BANDS.map((b) => b.colour));
    // Resemblance is 0.02 in all three: the band came from suitability, not
    // from the number the old layer painted.
    expect(top?.fillColor).not.toBe(low?.fillColor);
  });

  it('falls back to the purple resemblance scale when no suitability scale exists', () => {
    // The live state anywhere the utilisation artifact is not mounted. Blanking
    // the layer over a missing file would remove a working map.
    const [cell] = plannerPredictionsToPolygons([pred('a', 0.30, false, null)], cells('a'), unbanded);
    expect(SUITABILITY_BANDS.map((b) => b.colour)).not.toContain(cell?.fillColor);
    expect(cell?.fillColor).toBe(RESEMBLANCE_BANDS[0].colour);
  });

  it('never bands a cell whose own suitability is missing, even with a scale', () => {
    // A scale says how to band; it cannot supply the value being banded.
    const [cell] = plannerPredictionsToPolygons([pred('a', 0.30, false, null)], cells('a'), banded);
    expect(SUITABILITY_BANDS.map((b) => b.colour)).not.toContain(cell?.fillColor);
  });

  it('keeps a built cell slate whichever palette is in play', () => {
    for (const scale of [banded, unbanded]) {
      const [built] = plannerPredictionsToPolygons(
        [pred('a', 0.95, true, 0.99)], cells('a'), scale);
      expect(built?.fillColor).toBe(BUILT_COLOUR);
    }
  });

  it('draws an already-built cell off the resemblance scale entirely', () => {
    // These are the cells the model ranks highest: measured on real circles
    // around Sudirman, Cibubur and Serpong, the three top-scoring cells all had
    // a station. On the shared scale they would read as the best candidates in
    // the circle, which is the opposite of what they are.
    const [built] = plannerPredictionsToPolygons([pred('a', 0.95, true)], cells('a'), unbanded);
    const [best] = plannerPredictionsToPolygons([pred('a', 0.30)], cells('a'), unbanded);
    expect(built?.fillColor).toBe(BUILT_COLOUR);
    expect(built?.fillColor).not.toBe(best?.fillColor);
    expect(built?.weight ?? 0).toBeGreaterThan(best?.weight ?? 0);
  });
});
