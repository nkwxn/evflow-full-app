import type {
  PlannerCandidateApi,
  PlannerPredictionApi,
  PlannerCellsGeoJsonResponse,
  PlannerGeoJsonGeometry,
  StationApiItem
} from '@evflow/shared';
import type { LeafletMapMarker, LeafletPolygonLayer } from '@evflow/ui';
import type { DemandPriority, OptimalSite } from './demandHeatmap';
import { BUILT_COLOUR, resemblanceColour, resemblanceOpacity } from './site-prediction/areaPrediction';
import { classOpacity, classify, type DensityScale } from './density/densityScale';

const priorityColors: Record<DemandPriority, string> = {
  high: '#ef4444',
  moderate: '#f59e0b',
  low: '#10b981'
};

export type PlannerLandUseMetric = 'commercial' | 'industrial' | 'residential' | 'retail';

const landUseColors: Record<PlannerLandUseMetric, string> = {
  commercial: '#0EA5E9',
  industrial: '#64748B',
  residential: '#8B5CF6',
  retail: '#F97316'
};

export function plannerCandidateToOptimalSite(candidate: PlannerCandidateApi): OptimalSite {
  return {
    id: candidate.cell_id,
    district: cleanAreaName(candidate.kota) ?? 'Jabodetabek',
    latitude: candidate.latitude,
    longitude: candidate.longitude,
    score: Math.round(clampUnit(candidate.score) * 100)
  };
}

export function plannerCellsToPolygons(response: PlannerCellsGeoJsonResponse): LeafletPolygonLayer[] {
  return response.features.flatMap((feature) => {
    const priority = scoreToDemandPriority(feature.properties.score ?? feature.properties.value ?? 0);
    return geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `${feature.properties.cell_id}-${index}`,
      coordinates: ring.map(([longitude, latitude]) => [latitude, longitude] as [number, number]),
      fillColor: priorityColors[priority],
      fillOpacity: 0.28,
      color: priorityColors[priority],
      weight: 0.6
    }));
  });
}

/**
 * A metric column drawn as a density surface.
 *
 * Classified into equal-count classes over the cells actually returned, not
 * scaled against the largest value on screen. The old scale was
 * `0.08 + sqrt(value / max) * 0.30`, which works only when the data reaches down
 * towards zero. Population inside a city does not: measured on a real Jakarta
 * viewport of 700 cells the values ran 4,032 (p25) to 10,656, so every cell
 * landed between opacity 0.29 and 0.38 and the layer rendered as one flat purple
 * sheet. See density/densityScale for why fixed regional breaks were not the
 * answer either.
 *
 * Returns the scale alongside the polygons so the legend can print the values at
 * each break. The colours are relative to the current view, which is the normal
 * trade for a choropleth and only misleads if the numbers are hidden.
 */
export function plannerCellsToMetricPolygons(
  response: PlannerCellsGeoJsonResponse,
  fillColor: string,
  idPrefix: string
): { polygons: LeafletPolygonLayer[]; scale: DensityScale | null } {
  const scale = classify(
    response.features
      .map((feature) => feature.properties.value)
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  );
  if (!scale) return { polygons: [], scale: null };

  const polygons = response.features.flatMap((feature) => {
    const value = feature.properties.value;
    if (typeof value !== 'number' || !Number.isFinite(value)) return [];
    return geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `${idPrefix}-${feature.properties.cell_id}-${index}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor,
      fillOpacity: classOpacity(scale.classOf(value)),
      // No per-cell outline. At 400 m across a city viewport that is thousands of
      // strokes, and they turned the surface into graph paper: the grid was the
      // most visible thing on the layer, and it carried no information at all.
      color: fillColor,
      weight: 0
    }));
  });

  return { polygons, scale };
}

export function plannerLandUseToPolygons(
  responses: Partial<Record<PlannerLandUseMetric, PlannerCellsGeoJsonResponse>>
): LeafletPolygonLayer[] {
  const cells = new Map<string, {
    feature: PlannerCellsGeoJsonResponse['features'][number];
    metric: PlannerLandUseMetric;
    value: number;
  }>();

  (Object.entries(responses) as Array<[PlannerLandUseMetric, PlannerCellsGeoJsonResponse]>).forEach(([metric, response]) => {
    response.features.forEach((feature) => {
      const value = feature.properties.value ?? 0;
      const existing = cells.get(feature.properties.cell_id);
      if (value > 0 && (!existing || value > existing.value)) {
        cells.set(feature.properties.cell_id, { feature, metric, value });
      }
    });
  });

  return Array.from(cells.values()).flatMap(({ feature, metric, value }) =>
    geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `land-use-${feature.properties.cell_id}-${index}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor: landUseColors[metric],
      fillOpacity: 0.12 + Math.min(value, 1) * 0.26,
      color: landUseColors[metric],
      weight: 0.4
    }))
  );
}

/**
 * Model probabilities drawn on the cells they belong to.
 *
 * The prediction endpoint returns cell_id and probability and no geometry, so
 * the shapes come from the cells.geojson response the map already loads and the
 * two are joined by cell_id here.
 *
 * A cell with no prediction gets NO polygon rather than a neutral one. The
 * predictions list is trimmed by `top`, so an unmatched cell means "not in the
 * top N", and painting it any colour at all would state a result the request
 * never asked for.
 *
 * Cells that already have a station are drawn in slate with a heavier border,
 * deliberately outside the resemblance scale. They are the cells the model
 * ranks highest, so on the shared scale they would read as the strongest
 * candidates in the circle, which is the opposite of what they are.
 */
export function plannerPredictionsToPolygons(
  predictions: PlannerPredictionApi[],
  cells: PlannerCellsGeoJsonResponse,
  /**
   * The region-wide ceiling the shading is scaled against, from the response.
   * Passed in rather than remembered so the colours and the caption below the
   * map cannot disagree after a retrain moves the ceiling.
   */
  ceiling: number | null
): LeafletPolygonLayer[] {
  const byCell = new Map(predictions.map(
    (p) => [p.cell_id, { probability: p.probability, built: p.has_station }]));

  return cells.features.flatMap((feature) => {
    const hit = byCell.get(feature.properties.cell_id);
    if (hit === undefined) return [];
    const { probability, built } = hit;
    return geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `prediction-${feature.properties.cell_id}-${index}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor: built ? BUILT_COLOUR : resemblanceColour(probability, ceiling),
      fillOpacity: built ? 0.22 : resemblanceOpacity(probability, ceiling),
      color: built ? BUILT_COLOUR : resemblanceColour(probability, ceiling),
      weight: built ? 0.9 : 0.4
    }));
  });
}

export function plannerStationsToMarkers(stations: StationApiItem[]): LeafletMapMarker[] {
  return stations.map((station) => ({
    id: `station:${station.id}`,
    label: station.name ?? 'Existing SPKLU',
    latitude: station.latitude,
    longitude: station.longitude,
    type: 'station'
  }));
}

export function scoreToDemandPriority(score: number): DemandPriority {
  if (score >= 0.75) return 'high';
  if (score >= 0.5) return 'moderate';
  return 'low';
}

export function plannerViewportBbox(viewport: { west: number; south: number; east: number; north: number }) {
  return `${viewport.west},${viewport.south},${viewport.east},${viewport.north}`;
}

function geometryOuterRings(geometry: PlannerGeoJsonGeometry): number[][][] {
  if (geometry.type === 'Polygon') {
    const polygon = geometry.coordinates as number[][][];
    return polygon.length ? [polygon[0] ?? []] : [];
  }
  const multiPolygon = geometry.coordinates as number[][][][];
  return multiPolygon.map((polygon) => polygon[0] ?? []).filter((ring) => ring.length > 0);
}

function toLeafletCoordinates(ring: number[][]): Array<[number, number]> {
  return ring.map(([longitude, latitude]) => [latitude, longitude]);
}

function cleanAreaName(value: string | null) {
  return value?.replace(/^(Kota|Kabupaten)\s+/i, '').trim() || null;
}

function clampUnit(value: number) {
  return Math.min(Math.max(value, 0), 1);
}
