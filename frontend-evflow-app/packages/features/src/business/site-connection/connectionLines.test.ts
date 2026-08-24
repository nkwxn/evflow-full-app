import { describe, expect, it } from 'vitest';
import type { NearbyStationBenchmark } from '../site-feasibility/siteFeasibilityTypes';
import {
  MEMBERSHIP_COLOUR, competitionLines, membershipLines, plannerConnectionLines
} from './connectionLines';

const CENTRE = { latitude: -6.2088, longitude: 106.8206 };
const SITE = { id: 'JBDTBK_21737', latitude: -6.1787, longitude: 106.8183 };

function station(over: Partial<NearbyStationBenchmark> & { id: string; distanceKm: number }): NearbyStationBenchmark {
  return {
    name: `SPKLU ${over.id}`, latitude: -6.19, longitude: 106.82,
    averageDailySessions: 1, dailySessionsTrendPct: 0,
    monthlyRevenueIdr: 1, monthlyRevenueTrendPct: 0,
    ...over
  } as NearbyStationBenchmark;
}

describe('membership lines', () => {
  it('links the chosen point to every suggestion in its circle', () => {
    const lines = membershipLines(CENTRE, [SITE, { ...SITE, id: 'b' }]);
    expect(lines).toHaveLength(2);
    expect(lines.every((l) => l.color === MEMBERSHIP_COLOUR)).toBe(true);
  });

  it('hands Leaflet latitude first', () => {
    // Backwards puts every line in the Indian Ocean: obvious on a map, and
    // invisible to a test that only counts lines.
    const [line] = membershipLines(CENTRE, [SITE]);
    expect(line.from).toEqual([-6.2088, 106.8206]);
    expect(line.to).toEqual([-6.1787, 106.8183]);
  });

  it('draws nothing before a point has been chosen', () => {
    expect(membershipLines(null, [SITE])).toEqual([]);
  });

  it('stays off the pressure scale, because membership is not a verdict', () => {
    const [line] = membershipLines(CENTRE, [SITE]);
    expect(['#EF4444', '#F59E0B']).not.toContain(line.color);
    expect(line.color).toBe('#10B981');
  });

  it('is the only kind of line that moves', () => {
    // Motion draws the eye. It belongs on "these came from the place you
    // tapped" and not on a line reporting a fixed distance to a competitor.
    const [member] = membershipLines(CENTRE, [SITE]);
    const [rival] = competitionLines(SITE, [station({ id: 'a', distanceKm: 0.4 })]);
    expect(member.animated).toBe(true);
    expect(rival.animated).toBeFalsy();
  });
});

describe('competition lines', () => {
  it('colours by distance band and thickens the close ones', () => {
    const near = competitionLines(SITE, [station({ id: 'a', distanceKm: 0.4 })])[0];
    const far = competitionLines(SITE, [station({ id: 'b', distanceKm: 4 })])[0];
    expect(near.color).toBe('#EF4444');
    expect(far.color).toBe('#94A3B8');
    expect(near.weight ?? 0).toBeGreaterThan(far.weight ?? 0);
  });

  it('labels each line with the distance and the station it reaches', () => {
    const [line] = competitionLines(SITE, [station({ id: 'a', distanceKm: 0.635, name: 'SPBU Abdul' })]);
    expect(line.label).toContain('635 m');
    expect(line.label).toContain('SPBU Abdul');
  });

  it('skips a station with no coordinates rather than guessing a position', () => {
    // The benchmark endpoint returned distance long before it returned lat/lon.
    // A line drawn at a guessed point would be a measurement nobody made.
    const lines = competitionLines(SITE, [
      station({ id: 'a', distanceKm: 1, latitude: undefined, longitude: undefined }),
      station({ id: 'b', distanceKm: 2 })
    ]);
    expect(lines).toHaveLength(1);
    expect(lines[0].id).toContain('b');
  });

  it('draws nothing when no suggestion is selected', () => {
    expect(competitionLines(null, [station({ id: 'a', distanceKm: 1 })])).toEqual([]);
  });
});

describe('what the map shows at each step', () => {
  it('shows membership while nothing is selected', () => {
    const lines = plannerConnectionLines({
      centre: CENTRE, sites: [SITE], selected: null, stations: []
    });
    expect(lines).toHaveLength(1);
    expect(lines[0].color).toBe(MEMBERSHIP_COLOUR);
  });

  it('swaps to competition once a suggestion is selected', () => {
    // Both at once is a thicket, and the question has changed: not "which
    // suggestions are mine" but "what is this one up against".
    const lines = plannerConnectionLines({
      centre: CENTRE, sites: [SITE, { ...SITE, id: 'b' }], selected: SITE,
      stations: [station({ id: 'a', distanceKm: 0.4 })]
    });
    expect(lines).toHaveLength(1);
    expect(lines[0].id).toContain('rival');
  });

  it('shows nothing at all before a point is chosen', () => {
    expect(plannerConnectionLines({
      centre: null, sites: [], selected: null, stations: []
    })).toEqual([]);
  });
});
