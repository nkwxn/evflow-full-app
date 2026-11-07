import type { LeafletTileOverlay } from '@evflow/ui';

/**
 * TomTom's live traffic flow, as a tile layer over our base map.
 *
 * WHAT THIS SHOWS, AND WHAT IT DOES NOT
 *
 * Flow tiles colour each road by how its current speed compares with its
 * free-flow speed. That is congestion, measured minute by minute from TomTom's
 * own fleet, and it is REAL data -- worth saying out loud in this codebase,
 * where every charging session is simulation output.
 *
 * It is not, on its own, a siting input. Congestion says cars are slow here, not
 * that they stop here, and a charger wants the second. TomTom's Incident Details
 * endpoint returns structured delay per segment and could feed the weighted
 * score properly; this layer is the map view that was asked for, not that.
 *
 * WHY THE KEY IS IN THE URL AND WHY THAT IS FINE
 *
 * TomTom puts the key in the tile path, so it ships in the bundle and any user
 * can read it, exactly like EXPO_PUBLIC_DEMO_PASSWORD already does. Secrecy was never
 * the control here: the key must be domain-restricted in the TomTom console,
 * after which reading it buys nothing. Proxying tiles through our own API would
 * hide it, at the cost of routing roughly twenty tiles per pan through a VPS
 * with fifteen database connections.
 */

/**
 * Style over a light base map.
 *
 * COLOURS, FROM TOMTOM'S OWN DOCUMENTATION
 *   green         free-flowing
 *   yellow/orange slower than usual
 *   red           heavy congestion
 *   dark grey     road closed
 *
 * `relative0-dark` compares current speed against that road's own free-flow
 * speed, so the colour means "slower than this road normally runs" rather than
 * "slow in absolute terms". A 40 km/h side street at 40 km/h is green; a toll
 * road at 40 km/h is red. That is the right question for siting.
 *
 * It draws EVERY road, not only the congested ones. An earlier version of this
 * comment claimed otherwise; that is `relative-delay`, a different style. The
 * consequence is worth knowing when reading the map: a screen full of green is
 * the normal, healthy picture, not a layer failing to load.
 *
 * `absolute` was rejected because it colours by raw speed, so every residential
 * street reads as congested next to a motorway.
 *
 * WHY relative-delay AND NOT relative0-dark
 *
 * relative0-dark draws every road, so a healthy city is a screen full of green.
 * That green competes with the green dashed lines this dashboard already uses to
 * link a chosen point to its suggestions, and it buries the handful of amber and
 * red segments that are the only part a planner acts on. relative-delay draws
 * ONLY the roads that differ from free flow, so what remains on screen is the
 * problem itself.
 *
 * The cost is that an empty layer becomes ambiguous: no congestion and no data
 * look the same. The legend says so out loud rather than leaving it to be
 * guessed.
 */
const FLOW_STYLE = 'relative-delay';

/**
 * Line width, in TomTom's own units.
 *
 * The tiles are raster, so this cannot be set in CSS or Leaflet -- the width is
 * drawn server-side and the only handle is this parameter. TomTom's default is
 * 10, which at Jakarta's road density paints bands wide enough to hide the
 * street grid, the demand cells and the site markers underneath them. The layer
 * is context for the planner's own data, so it must not outweigh it.
 *
 * Measured against tile 14/13053/8473 (central Jakarta): thickness 10 returns
 * 27,605 bytes and is byte-identical to omitting the parameter, confirming 10 is
 * the default; 4 returns 25,430 and 2 returns 22,567. The API validates the
 * range -- 99 is rejected with HTTP 400 -- so this is a real parameter and not
 * one silently ignored.
 */
const LINE_THICKNESS = 4;

/** v4 is the generally available Traffic API. Orbis v2 needs a separate entitlement. */
const VERSION = 4;

/** TomTom's terms require this wherever their data is displayed. */
export const TOMTOM_ATTRIBUTION =
  '&copy; <a href="https://www.tomtom.com/">TomTom</a> traffic';

/** Reads the build-time key. Empty, absent or placeholder all mean "no traffic". */
export function tomtomKey(env: Record<string, string | undefined> | undefined): string | null {
  const key = env?.EXPO_PUBLIC_TOMTOM_API_KEY?.trim();
  return key ? key : null;
}

/**
 * The traffic overlay, or null when there is no key.
 *
 * Null rather than a broken layer: without a key every tile comes back 403, and
 * a map quietly pocked with missing squares is worse than a layer that never
 * offered itself. The toggle is hidden in the same case.
 */
export function trafficOverlay(key: string | null, opacity = 0.85): LeafletTileOverlay | null {
  if (!key) return null;
  return {
    id: 'tomtom-traffic-flow',
    url: `https://api.tomtom.com/traffic/map/${VERSION}/tile/flow/${FLOW_STYLE}/{z}/{x}/{y}.png`
      + `?key=${encodeURIComponent(key)}&thickness=${LINE_THICKNESS}`,
    attribution: TOMTOM_ATTRIBUTION,
    opacity,
    // TomTom serves flow tiles to z22; the base map stops at 19, and a traffic
    // layer outliving the map under it would float over blank tiles.
    maxZoom: 19
  };
}

/**
 * What the traffic colours mean, for the legend.
 *
 * Taken from TomTom's own documentation rather than read off the map. Green is
 * absent on purpose: relative-delay draws only roads that differ from free flow,
 * so a road running normally is simply not painted.
 */
export const TRAFFIC_LEGEND: Array<{ colour: string; label: string }> = [
  { colour: '#B91C1C', label: 'Closed' },
  { colour: '#EF4444', label: 'Heavy congestion' },
  { colour: '#F97316', label: 'Slow' },
  { colour: '#FACC15', label: 'Slightly slow' }
];

/** Said out loud because an empty layer is otherwise indistinguishable from a broken one. */
export const TRAFFIC_EMPTY_NOTE = 'Roads running normally are not drawn';
