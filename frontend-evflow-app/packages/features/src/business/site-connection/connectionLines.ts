import type { LeafletConnectionLine } from '@evflow/ui';
import type { NearbyStationBenchmark } from '../site-feasibility/siteFeasibilityTypes';
import { competitivePressure, formatDistance, type Pressure } from './competitiveLandscape';

/**
 * Connection lines drawn on the map itself.
 *
 * WHY ON THE MAP AND NOT IN A DIAGRAM
 *
 * A node-link panel can show the same distances, but it cannot show them where
 * they are. "Three competitors within a kilometre" means something different
 * when all three sit on the same arterial road than when they ring the site from
 * three directions, and only the map carries that.
 *
 * TWO KINDS OF LINE, ON PURPOSE
 *
 * From the chosen point to each suggestion: these belong to your circle. Grey
 * and thin, because they carry no judgement, only membership.
 *
 * From a selected suggestion to the SPKLU already around it: this is what the
 * site would be up against. Coloured by distance band, because that is the part
 * a viability score of 70 does not tell you.
 *
 * Pure so the geometry is testable without a map, which is the only way to catch
 * latitude and longitude being handed over the wrong way round: Leaflet takes
 * latitude first, and getting it backwards puts every line in the Indian Ocean.
 */

/**
 * Green, and deliberately not on the red/amber/grey pressure scale.
 *
 * These links carry no judgement, only membership, so they must not borrow a
 * colour that means "close competitor". Green also reads as the neutral end of
 * the palette already used for cell scores, so nothing new has to be learned.
 */
export const MEMBERSHIP_COLOUR = '#10B981';

const PRESSURE_COLOUR: Record<Pressure, string> = {
  high: '#EF4444',
  moderate: '#F59E0B',
  low: '#94A3B8'
};

/**
 * Lines from the point the planner chose to each suggestion in its circle.
 *
 * Without these the suggestions are loose pins: nothing on screen says they came
 * from the place that was tapped, and a planner who has panned away cannot tell
 * which analysis they are looking at.
 */
export function membershipLines(
  centre: { latitude: number; longitude: number } | null,
  sites: Array<{ id: string; latitude: number; longitude: number }>
): LeafletConnectionLine[] {
  if (!centre) return [];
  return sites.map((site) => ({
    id: `member-${site.id}`,
    from: [centre.latitude, centre.longitude],
    to: [site.latitude, site.longitude],
    color: MEMBERSHIP_COLOUR,
    weight: 1.6,
    dashed: true,
    // Only these move. Motion draws the eye, and it belongs on the links that
    // say "these came from the place you tapped" rather than on the ones
    // reporting a fixed distance to a competitor.
    animated: true
  }));
}

/**
 * Lines from one suggestion to the existing stations around it.
 *
 * Stations with no coordinates are skipped rather than drawn at a guessed
 * position. The benchmark endpoint returns distance for every station but
 * latitude and longitude only since they were added to it; anything without them
 * still appears in the list below the map, just not as a line.
 */
export function competitionLines(
  site: { id: string; latitude: number; longitude: number } | null,
  stations: NearbyStationBenchmark[]
): LeafletConnectionLine[] {
  if (!site) return [];
  return stations
    .filter((s) => typeof s.latitude === 'number' && typeof s.longitude === 'number')
    .map((station) => {
      const pressure = competitivePressure(station.distanceKm);
      return {
        id: `rival-${site.id}-${station.id}`,
        from: [site.latitude, site.longitude] as [number, number],
        to: [station.latitude as number, station.longitude as number] as [number, number],
        color: PRESSURE_COLOUR[pressure],
        weight: pressure === 'high' ? 2.4 : 1.6,
        dashed: true,
        label: `${formatDistance(station.distanceKm)} · ${station.name}`
      };
    });
}

/**
 * Everything the map should draw, in one list.
 *
 * Membership lines drop away once a suggestion is selected. Both sets at once is
 * a thicket, and the question has changed by then: not "which suggestions are
 * mine" but "what is this one up against".
 */
export function plannerConnectionLines(input: {
  centre: { latitude: number; longitude: number } | null;
  sites: Array<{ id: string; latitude: number; longitude: number }>;
  selected: { id: string; latitude: number; longitude: number } | null;
  stations: NearbyStationBenchmark[];
}): LeafletConnectionLine[] {
  if (input.selected) return competitionLines(input.selected, input.stations);
  return membershipLines(input.centre, input.sites);
}
