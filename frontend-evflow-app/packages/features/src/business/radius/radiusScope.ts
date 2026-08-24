/**
 * Confining every map layer to the circle the planner drew.
 *
 * WHY LAYERS FOLLOW A CIRCLE AND NOT THE VIEWPORT
 *
 * A viewport is whatever the window happens to be showing: it changes when the
 * planner resizes the browser, and two places can never be compared because the
 * area under each is different. A circle around a chosen point is the question
 * being asked -- "what is here, within this far" -- and it stays the same
 * question at any zoom.
 *
 * Before a point is chosen there is no circle, so layers stay on the viewport.
 * That is deliberate: the heatmap is what tells a planner where to click in the
 * first place, and it cannot do that if it only appears after the click.
 *
 * WHY THE CLIP IS DONE HERE AND NOT IN SQL
 *
 * The bounding box of a circle is already the same order of magnitude as the
 * circle: a 3 km radius covers about 140 cells against 5,242 for a Jakarta
 * viewport, so fetching the box captures nearly all of the payload saving. What
 * is left is the corners, 27% more area than the circle inscribed in it, and
 * dropping those client-side costs one comparison per feature instead of a new
 * radius parameter on three separate endpoints, two of which the driver app
 * also uses.
 */

/** One degree of latitude in km. Longitude shrinks with the cosine of latitude. */
const KM_PER_DEGREE = 111.32;

export type Centre = { latitude: number; longitude: number };
export type Bbox = { west: number; south: number; east: number; north: number };

/**
 * The smallest box containing the circle.
 *
 * Longitude is divided by cos(latitude) because meridians converge. At
 * Jabodetabek's latitude that is only a 0.6% correction, but it is free.
 */
export function circleBbox(centre: Centre, radiusKm: number): Bbox {
  const dLat = radiusKm / KM_PER_DEGREE;
  const dLon = radiusKm / (KM_PER_DEGREE * Math.cos((centre.latitude * Math.PI) / 180));
  return {
    west: centre.longitude - dLon,
    east: centre.longitude + dLon,
    south: centre.latitude - dLat,
    north: centre.latitude + dLat
  };
}

/**
 * Great-circle distance in km, by the haversine formula.
 *
 * Not a flat-earth approximation. Over 10 km the difference is small, but this
 * same function decides what a planner sees inside the circle and what falls
 * outside it, and a cell that flickers across the boundary is worse than the
 * arithmetic is expensive.
 */
export function distanceKm(a: Centre, b: Centre): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const lat1 = toRad(a.latitude);
  const lat2 = toRad(b.latitude);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function withinRadius(centre: Centre, radiusKm: number, point: Centre): boolean {
  return distanceKm(centre, point) <= radiusKm;
}

/**
 * Keep only the items whose position falls inside the circle.
 *
 * An item whose position cannot be read is DROPPED, not kept. Something drawn
 * without knowing where it is would be inside the circle only by accident, and
 * the point of the circle is that everything in it is genuinely there.
 */
export function clipToRadius<T>(
  items: T[],
  centre: Centre | null,
  radiusKm: number,
  positionOf: (item: T) => Centre | null
): T[] {
  if (!centre) return items;
  return items.filter((item) => {
    const position = positionOf(item);
    return position ? withinRadius(centre, radiusKm, position) : false;
  });
}

/** Radius bounds for the slider, in km. */
export const RADIUS_MIN_KM = 0.5;
export const RADIUS_MAX_KM = 10;
export const RADIUS_STEP_KM = 0.5;
export const RADIUS_DEFAULT_KM = 3;

/** "800 m" below a kilometre, "3.5 km" above: metres are what decide a site. */
export function formatRadius(radiusKm: number): string {
  return radiusKm < 1 ? `${Math.round(radiusKm * 1000)} m` : `${radiusKm} km`;
}

/**
 * Approximate centre of a GeoJSON ring, as the mean of its vertices.
 *
 * Cells arrive as polygons and carry no centre of their own, so the clip needs
 * one. The mean of the corners is not the true centroid of an arbitrary polygon,
 * but these are 400 m grid squares: the difference is metres, against a radius
 * measured in kilometres.
 *
 * GeoJSON is [longitude, latitude]. Reading them the other way round puts every
 * cell in the Indian Ocean, so the swap happens here once rather than at each
 * call site.
 */
export function ringCentre(ring: number[][]): Centre | null {
  if (!ring?.length) return null;
  let lon = 0;
  let lat = 0;
  for (const point of ring) {
    if (!Array.isArray(point) || point.length < 2) return null;
    lon += point[0];
    lat += point[1];
  }
  return { latitude: lat / ring.length, longitude: lon / ring.length };
}

/** The outer ring of a Polygon or the first ring of a MultiPolygon. */
export function geometryCentre(geometry: { type: string; coordinates: unknown }): Centre | null {
  if (geometry?.type === 'Polygon') {
    const rings = geometry.coordinates as number[][][];
    return rings?.length ? ringCentre(rings[0]) : null;
  }
  if (geometry?.type === 'MultiPolygon') {
    const polygons = geometry.coordinates as number[][][][];
    return polygons?.length && polygons[0]?.length ? ringCentre(polygons[0][0]) : null;
  }
  return null;
}
