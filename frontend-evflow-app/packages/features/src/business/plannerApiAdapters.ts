import type {
  PlannerLandUseResponse,
  PlannerCandidateApi,
  PlannerPredictionApi,
  PlannerCellsGeoJsonResponse,
  PlannerGeoJsonGeometry,
  StationApiItem
} from '@evflow/shared';
import type { LeafletMapMarker, LeafletPolygonLayer } from '@evflow/ui';
import type { OptimalSite } from './demandHeatmap';
import {
  BUILT_COLOUR, resemblanceColour, resemblanceOpacity, suitabilityColour, suitabilityOpacity
} from './site-prediction/areaPrediction';
import type { SuitabilityScale } from './site-prediction/areaPrediction';
import { classOpacity, classify, type DensityScale } from './density/densityScale';


export type PlannerLandUseMetric = 'commercial' | 'industrial' | 'residential' | 'retail';

/**
 * One colour per class, opaque enough to read as a category.
 *
 * The old layer tinted 500 m squares by a blended share, so a colour meant
 * "mostly residential, a bit commercial" and no legend could name it. These are
 * polygons of exactly one class each, so a colour means one thing and the
 * legend is a list rather than a gradient.
 *
 * Chosen apart from every other layer on this map: the heatmap is purple, live
 * traffic is red/amber/green, population is magenta, built cells are slate. Land
 * use had to avoid all four and still separate four classes from each other.
 */
export const landUseColors: Record<PlannerLandUseMetric, string> = {
  commercial: '#0EA5E9',
  industrial: '#78716C',
  residential: '#FCD34D',
  retail: '#F97316'
};

/**
 * Filled, not tinted.
 *
 * A share-shaded square had to stay faint or it hid the base map underneath.
 * A polygon that follows a real boundary can carry colour, and needs to: the
 * shapes are the information now.
 */
const LAND_USE_FILL_OPACITY = 0.55;

export function plannerLandUsePolygons(
  response: PlannerLandUseResponse
): LeafletPolygonLayer[] {
  return response.features.flatMap((feature, index) => {
    let geometry: PlannerCellsGeoJsonResponse['features'][number]['geometry'];
    try {
      geometry = JSON.parse(feature.geojson);
    } catch {
      // A polygon the server could not serialise is one polygon, not a reason to
      // drop the layer. Skipping it leaves a hole; failing loses the city.
      return [];
    }
    const colour = landUseColors[feature.landuse as PlannerLandUseMetric] ?? '#94A3B8';
    return geometryOuterRings(geometry).map((ring, ringIndex) => ({
      id: `land-use-${index}-${ringIndex}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor: colour,
      fillOpacity: LAND_USE_FILL_OPACITY,
      color: colour,
      weight: 0.3
    }));
  });
}

export function plannerCandidateToOptimalSite(candidate: PlannerCandidateApi): OptimalSite {
  return {
    id: candidate.cell_id,
    district: cleanAreaName(candidate.kota) ?? 'Jabodetabek',
    latitude: candidate.latitude,
    longitude: candidate.longitude,
    score: Math.round(clampUnit(candidate.score) * 100)
  };
}

// plannerCellsToPolygons and scoreToDemandPriority used to live here: a second
// red/amber/green painter, cutting its bands at a hardcoded 0.75 and 0.5 on the
// weighted SQL score. Nothing called it after f72afdd.
//
// It was the obvious thing to repurpose for the suitability layer, and that is
// exactly why it is gone. Its thresholds were constants, and the whole point of
// the band floors travelling with the response is that a retrain or a station
// import moves them. Keeping a hardcoded-threshold painter beside an
// API-floor-driven one would rebuild the divergence this layer was rewritten to
// close -- two functions producing the same palette from different rules.

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
 * deliberately outside either scale. A slate cell says "a station stands here",
 * which is more specific than the green beside it saying "stations are near",
 * and both mean do not build.
 *
 * TWO PALETTES, AND WHY BOTH ARE STILL HERE
 *
 * Red/amber/green is suitability: the model's demand ranking blended with a
 * discount for what is already built nearby. That is what this layer is for.
 *
 * Purple is resemblance, and it is the fallback when no suitability scale could
 * be built — which is the live state anywhere the utilisation artifact is not
 * mounted. Blanking the layer there would remove a working map over a missing
 * file. The palettes are deliberately nothing alike, so a reader can always tell
 * which question is on screen; a shared palette is how these two came to be
 * confused for each other in the first place.
 */
export function plannerPredictionsToPolygons(
  predictions: PlannerPredictionApi[],
  cells: PlannerCellsGeoJsonResponse,
  /**
   * Both scales, from the response rather than remembered, so the colours and
   * the legend beneath the map cannot disagree after a retrain moves either.
   */
  scale: { suitability: SuitabilityScale | null; resemblanceCeiling: number | null }
): LeafletPolygonLayer[] {
  const byCell = new Map(predictions.map((p) => [p.cell_id, p]));

  return cells.features.flatMap((feature) => {
    const hit = byCell.get(feature.properties.cell_id);
    if (hit === undefined) return [];
    const banded = hit.has_station ? null : suitabilityColour(hit.suitability, scale.suitability);
    const fill = hit.has_station ? BUILT_COLOUR
      : banded ?? resemblanceColour(hit.probability, scale.resemblanceCeiling);
    const opacity = hit.has_station ? 0.22
      : banded ? suitabilityOpacity(hit.suitability)
      : resemblanceOpacity(hit.probability, scale.resemblanceCeiling);
    return geometryOuterRings(feature.geometry).map((ring, index) => ({
      id: `prediction-${feature.properties.cell_id}-${index}`,
      coordinates: toLeafletCoordinates(ring),
      fillColor: fill,
      fillOpacity: opacity,
      color: fill,
      weight: hit.has_station ? 0.9 : 0.4
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
