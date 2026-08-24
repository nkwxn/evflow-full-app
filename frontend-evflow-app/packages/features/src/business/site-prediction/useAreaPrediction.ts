import { useEffect, useState } from 'react';
import { fetchPlannerAreaPrediction, fetchPlannerCells } from '@evflow/shared';
import type {
  PlannerAreaDistributionApi,
  PlannerModelInfoApi
} from '@evflow/shared';
import type { LeafletPolygonLayer } from '@evflow/ui';
import { plannerPredictionsToPolygons } from '../plannerApiAdapters';
import { plannerErrorCopy } from '../site-feasibility/useSiteFeasibilityDetail';
import { DRAW_LIMIT, SCORE_LIMIT } from './areaPrediction';

export type AreaPredictionState = {
  polygons: LeafletPolygonLayer[];
  /** Cells actually drawn. Below distribution.cells_predicted when `top` trimmed the list. */
  drawnCells: number;
  distribution: PlannerAreaDistributionApi | null;
  model: PlannerModelInfoApi | null;
  interpretation: string | null;
  loading: boolean;
  error: string | null;
};

const idle: AreaPredictionState = {
  polygons: [], drawnCells: 0, distribution: null, model: null,
  interpretation: null, loading: false, error: null
};

/** One degree of latitude, in km. Longitude shrinks with the cosine of latitude. */
const KM_PER_DEGREE = 111.32;

/**
 * Score the cells around a point the planner chose, whenever that choice changes.
 *
 * A circle rather than the viewport. "Analyse around here" is the question a
 * planner asks; a viewport answers "whatever is on screen", which moves when
 * they resize the window and cannot be compared between two places.
 *
 * COMPUTED PER REQUEST, NOT READ FROM A LAYER
 *
 * The whole 28,176-cell grid scores in roughly 155 ms server-side, and a 3 km
 * circle in about 25 ms of SQL. Precomputing buys no speed at that cost and
 * introduces staleness nothing on a map can show: a probability frozen before
 * the last POI reload looks exactly like a fresh one.
 *
 * TWO REQUESTS, ON PURPOSE
 *
 * The prediction endpoint returns cell_id and probability with no geometry;
 * cells.geojson returns geometry. Joining here keeps polygon rings out of the
 * prediction payload, which the map already holds. The geometry request covers
 * the circle's bounding BOX, so its corners fall outside the circle and get no
 * prediction: plannerPredictionsToPolygons drops them rather than drawing them,
 * which is what keeps the drawn shape a circle.
 */
export function useAreaPrediction(
  centre: { latitude: number; longitude: number } | null,
  radiusKm: number,
  enabled: boolean
): AreaPredictionState {
  const [state, setState] = useState<AreaPredictionState>(idle);
  const lat = centre?.latitude ?? null;
  const lon = centre?.longitude ?? null;

  useEffect(() => {
    if (!enabled || lat === null || lon === null) {
      setState(idle);
      return undefined;
    }

    const controller = new AbortController();
    // Long enough that changing the radius twice in a row issues one request.
    // An aborted request still runs to completion on the server, and the engine
    // pools 15 connections, so queued work nobody is waiting for is what took
    // the API down for 30 seconds during an earlier test.
    const timer = setTimeout(() => {
      setState((previous) => ({ ...previous, loading: true, error: null }));

      const dLat = radiusKm / KM_PER_DEGREE;
      const dLon = radiusKm / (KM_PER_DEGREE * Math.cos((lat * Math.PI) / 180));

      Promise.all([
        fetchPlannerAreaPrediction({
          latitude: lat, longitude: lon, radiusKm,
          limit: SCORE_LIMIT, top: DRAW_LIMIT, signal: controller.signal
        }),
        fetchPlannerCells({
          west: lon - dLon, east: lon + dLon, south: lat - dLat, north: lat + dLat,
          limit: 10_000, metric: 'score', signal: controller.signal
        })
      ])
        .then(([prediction, cells]) => {
          if (controller.signal.aborted) return;
          setState({
            polygons: plannerPredictionsToPolygons(
              prediction.predictions, cells, prediction.distribution.resemblance_ceiling),
            drawnCells: prediction.predictions.length,
            distribution: prediction.distribution,
            model: prediction.model,
            interpretation: prediction.interpretation,
            loading: false,
            error: null
          });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || (error as Error)?.name === 'AbortError') return;
          // The previous circle's polygons are cleared rather than left on
          // screen. Stale shapes under a fresh error message read as a result
          // for the place now selected, which is the one thing this must never
          // imply.
          setState({ ...idle, error: plannerErrorCopy(error) });
        });
    }, 400);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, lat, lon, radiusKm]);

  return state;
}
