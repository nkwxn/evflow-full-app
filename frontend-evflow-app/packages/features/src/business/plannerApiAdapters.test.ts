import { describe, expect, it } from 'vitest';
import type { PlannerCandidateApi, PlannerCellsGeoJsonResponse, StationApiItem } from '@evflow/shared';
import {
  plannerCandidateToOptimalSite,
  plannerCellsToMetricPolygons,
  landUseColors,
  plannerCellsToPolygons,
  plannerLandUsePolygons,
  plannerPredictionsToPolygons,
  plannerStationsToMarkers,
  scoreToDemandPriority
} from './plannerApiAdapters';
import { BUILT_COLOUR } from './site-prediction/areaPrediction';

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

  it('swaps GeoJSON longitude/latitude into Leaflet latitude/longitude', () => {
    const response = {
      features: [{
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [[[106.8, -6.2], [106.81, -6.2], [106.8, -6.21], [106.8, -6.2]]] },
        properties: { cell_id: 'cell-1', kota: null, value: 0.8, score: 0.8, population: 1, poi_total: 1, station_count: 0, nearest_station_m: null }
      }]
    } as PlannerCellsGeoJsonResponse;
    const [polygon] = plannerCellsToPolygons(response);
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
    expect(polygon?.fillColor).toBe('#ef4444');
  });

  it('maps the documented frontend semantic bands at their boundaries', () => {
    expect(scoreToDemandPriority(0.75)).toBe('high');
    expect(scoreToDemandPriority(0.5)).toBe('moderate');
    expect(scoreToDemandPriority(0.49)).toBe('low');
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
  // sessions_per_connector_day is null here on purpose: this file is about
  // joining RESEMBLANCE onto cells, and the prescriptive number rides along
  // without taking part in that join.
  const pred = (cell_id: string, probability: number, has_station = false) =>
    ({ cell_id, kota: null, probability, has_station, sessions_per_connector_day: null });

  it('joins probabilities onto the cells they belong to', () => {
    const out = plannerPredictionsToPolygons([pred('b', 0.25)], cells('a', 'b'), CEILING);
    expect(out).toHaveLength(1);
    expect(out[0]?.id).toContain('b');
  });

  it('draws nothing for a cell with no prediction', () => {
    // The list is trimmed by `top`, so an unmatched cell means "not in the top
    // N". Painting it would state a result the request never asked for. It is
    // also what keeps the drawn shape a circle: the geometry request covers the
    // circle's bounding box, and its corners get no prediction.
    expect(plannerPredictionsToPolygons([], cells('a', 'b'), CEILING)).toHaveLength(0);
  });

  it('ignores a prediction whose cell is outside the loaded geometry', () => {
    expect(plannerPredictionsToPolygons([pred('elsewhere', 0.2)], cells('a'), CEILING)).toHaveLength(0);
  });

  it('swaps GeoJSON longitude/latitude into Leaflet order', () => {
    // Getting this backwards puts every cell in the Indian Ocean: obvious on a
    // map, invisible to a test that only counts polygons.
    const [polygon] = plannerPredictionsToPolygons([pred('a', 0.2)], cells('a'), CEILING);
    expect(polygon?.coordinates[0]).toEqual([-6.2, 106.8]);
  });

  it('grades unbuilt cells by resemblance', () => {
    const [low] = plannerPredictionsToPolygons([pred('a', 0.02)], cells('a'), CEILING);
    const [high] = plannerPredictionsToPolygons([pred('a', 0.30)], cells('a'), CEILING);
    expect(low?.fillColor).not.toBe(high?.fillColor);
    expect(high?.fillOpacity ?? 0).toBeGreaterThan(low?.fillOpacity ?? 0);
  });

  it('draws an already-built cell off the resemblance scale entirely', () => {
    // These are the cells the model ranks highest: measured on real circles
    // around Sudirman, Cibubur and Serpong, the three top-scoring cells all had
    // a station. On the shared scale they would read as the best candidates in
    // the circle, which is the opposite of what they are.
    const [built] = plannerPredictionsToPolygons([pred('a', 0.95, true)], cells('a'), CEILING);
    const [best] = plannerPredictionsToPolygons([pred('a', 0.30)], cells('a'), CEILING);
    expect(built?.fillColor).toBe(BUILT_COLOUR);
    expect(built?.fillColor).not.toBe(best?.fillColor);
    expect(built?.weight ?? 0).toBeGreaterThan(best?.weight ?? 0);
  });
});
