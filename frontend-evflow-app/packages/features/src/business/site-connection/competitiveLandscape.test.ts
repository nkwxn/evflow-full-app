import { describe, expect, it } from 'vitest';
import type { NearbyStationBenchmark } from '../site-feasibility/siteFeasibilityTypes';
import {
  MAX_COMPETITORS,
  PRESSURE_NEAR_KM,
  buildGraph,
  competitivePressure,
  formatDistance,
  pressureSummary,
  stationSublabel
} from './competitiveLandscape';

const SITE = { id: 'JBDTBK_20097', label: 'Jakarta Pusat', score: 70 };

function station(over: Partial<NearbyStationBenchmark> & { id: string; distanceKm: number }): NearbyStationBenchmark {
  return {
    name: `SPKLU ${over.id}`,
    // Generated fields. Present because the type carries them; nothing here may read them.
    averageDailySessions: 42, dailySessionsTrendPct: 7,
    monthlyRevenueIdr: 91_000_000, monthlyRevenueTrendPct: 4,
    ...over
  } as NearbyStationBenchmark;
}

describe('competitive pressure', () => {
  it('treats anything inside 1 km as competing for the same drivers', () => {
    expect(competitivePressure(0.4)).toBe('high');
    expect(competitivePressure(PRESSURE_NEAR_KM)).toBe('high');
  });

  it('separates a detour from a direct alternative', () => {
    expect(competitivePressure(1.01)).toBe('moderate');
    expect(competitivePressure(3)).toBe('moderate');
    expect(competitivePressure(3.01)).toBe('low');
  });
});

describe('distance formatting', () => {
  it('uses metres below a kilometre, where the difference decides things', () => {
    // "0.4 km" reads as far. "400 m" reads as across the road, which it is.
    expect(formatDistance(0.4)).toBe('400 m');
    expect(formatDistance(0.95)).toBe('950 m');
  });

  it('uses kilometres above that', () => {
    expect(formatDistance(2.34)).toBe('2.3 km');
  });
});

describe('what the diagram is allowed to say about a station', () => {
  it('shows operator, power and connectors, which come from the database', () => {
    const text = stationSublabel(station({
      id: 'a', distanceKm: 1, operator: 'PLN', powerKw: 50, totalConnectors: 2
    }));
    expect(text).toContain('PLN');
    expect(text).toContain('50 kW');
    expect(text).toContain('2 connectors');
  });

  it('never shows sessions or revenue', () => {
    // Both are produced by getMockNearbyStationPerformance, and every charging
    // session in staging and production is simulation output. On a diagram of
    // the competitive landscape they would read as measured demand.
    const s = station({ id: 'a', distanceKm: 1, operator: 'PLN', powerKw: 50, totalConnectors: 2 });
    const text = stationSublabel(s);
    expect(text).not.toContain('42');
    expect(text).not.toContain('91');
    expect(text.toLowerCase()).not.toContain('session');
    expect(text.toLowerCase()).not.toContain('revenue');
  });

  it('omits what the database does not have rather than printing a placeholder', () => {
    expect(stationSublabel(station({ id: 'a', distanceKm: 1 }))).toBe('');
    expect(stationSublabel(station({ id: 'a', distanceKm: 1, powerKw: 0 }))).toBe('');
  });
});

describe('summary line', () => {
  it('counts what is inside 1 km rather than averaging the distances', () => {
    // A mean of 2.4 km hides whether that is one at 200 m and one at 4.6 km.
    const text = pressureSummary([
      station({ id: 'a', distanceKm: 0.2 }),
      station({ id: 'b', distanceKm: 0.6 }),
      station({ id: 'c', distanceKm: 4.6 })
    ]);
    expect(text).toContain('2 SPKLU within 1 km');
    expect(text).toContain('200 m');
  });

  it('says plainly when nothing is close', () => {
    const text = pressureSummary([station({ id: 'a', distanceKm: 4.2 })]);
    expect(text).toContain('none within 1 km');
    expect(text).toContain('4.2 km');
  });

  it('says there is no competition rather than showing an empty diagram', () => {
    expect(pressureSummary([])).toMatch(/not be competing/i);
  });
});

describe('graph layout', () => {
  it('puts the candidate at the centre with its score', () => {
    const { nodes } = buildGraph(SITE, []);
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({ kind: 'site', x: 0, y: 0, sublabel: 'Viability 70' });
  });

  it('draws one edge per competitor, labelled with the real distance', () => {
    const { nodes, edges } = buildGraph(SITE, [
      station({ id: 'a', distanceKm: 0.4 }),
      station({ id: 'b', distanceKm: 2.2 })
    ]);
    expect(nodes).toHaveLength(3);
    expect(edges.map((e) => e.label)).toEqual(['400 m', '2.2 km']);
    expect(edges.every((e) => e.source === SITE.id)).toBe(true);
  });

  it('places a nearer competitor visually nearer', () => {
    // The ring radius tracks real distance. Uniform spacing would draw a station
    // 400 m away exactly like one 4 km away, which is the thing this diagram
    // exists to make visible.
    const { nodes } = buildGraph(SITE, [
      station({ id: 'near', distanceKm: 0.3 }),
      station({ id: 'far', distanceKm: 4.5 })
    ]);
    const dist = (id: string) => {
      const n = nodes.find((x) => x.id === id)!;
      return Math.hypot(n.x, n.y);
    };
    expect(dist('near')).toBeLessThan(dist('far'));
  });

  it('keeps the closest competitor off the centre node', () => {
    const { nodes } = buildGraph(SITE, [station({ id: 'a', distanceKm: 0.05 })]);
    const n = nodes.find((x) => x.id === 'a')!;
    expect(Math.hypot(n.x, n.y)).toBeGreaterThan(30);
  });

  it('orders competitors nearest first, so two sites can be compared at a glance', () => {
    const { edges } = buildGraph(SITE, [
      station({ id: 'far', distanceKm: 3 }),
      station({ id: 'near', distanceKm: 0.5 })
    ]);
    expect(edges[0]?.target).toBe('near');
  });

  it('caps how many it draws, and drops the furthest rather than an arbitrary slice', () => {
    const many = Array.from({ length: MAX_COMPETITORS + 5 }, (_, i) =>
      station({ id: `s${i}`, distanceKm: i + 1 }));
    const { nodes, edges } = buildGraph(SITE, many);
    expect(edges).toHaveLength(MAX_COMPETITORS);
    expect(nodes).toHaveLength(MAX_COMPETITORS + 1);
    expect(edges.map((e) => e.target)).not.toContain(`s${MAX_COMPETITORS + 4}`);
  });

  it('carries pressure onto both the node and its edge, so they cannot disagree', () => {
    const { nodes, edges } = buildGraph(SITE, [station({ id: 'a', distanceKm: 0.5 })]);
    expect(edges[0]?.pressure).toBe('high');
    expect(nodes.find((n) => n.id === 'a')?.pressure).toBe('high');
  });
});
