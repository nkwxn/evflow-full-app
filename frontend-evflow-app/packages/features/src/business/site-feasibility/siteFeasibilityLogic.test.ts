import { describe, expect, it, vi } from 'vitest';

vi.mock('react-native', () => ({ NativeModules: {} }));
import { generateMockOptimalSites, jakartaViewport } from '../demandHeatmap';
import {
  calculateActivityScore,
  calculateSiteScores,
  calculateLocationScore,
  calculateOverlapScore,
  calculatePoiScore,
  getHeatmapDescription,
  getLocationPriority,
  getRegionalResemblanceSummary,
  getNearbyStationsWithinRadius,
  getOverlapDescription,
  getPaybackStatus,
  getPoiDescription,
  formatRevenueIdr,
  resolveOptimalSite,
  sortStationsByDistance
} from './siteFeasibilityLogic';
import { getSiteFeasibility, plannerCellToSiteFeasibility } from './siteFeasibilityData';
import type { PlannerCellDetailApi } from '@evflow/shared';

describe('Epic 5 feasibility calculations', () => {
  it('calculates and caps the POI density score', () => {
    expect(calculatePoiScore(16)).toBe(80);
    expect(calculatePoiScore(20)).toBe(100);
    expect(calculatePoiScore(25)).toBe(100);
  });

  it('calculates and caps the network overlap score', () => {
    expect(calculateOverlapScore(4)).toBe(80);
    expect(calculateOverlapScore(5)).toBe(100);
    expect(calculateOverlapScore(6)).toBe(100);
  });

  it('combines road and residential activity points', () => {
    expect(calculateActivityScore('primary', 35)).toBe(85);
    expect(calculateActivityScore('secondary', 20)).toBe(55);
    expect(calculateActivityScore('local', 50)).toBe(65);
  });

  it('weights and rounds only the final location score', () => {
    expect(calculateLocationScore(88, 80, 95, 85)).toBe(86);
    expect(calculateLocationScore(81, 73, 67, 54)).toBe(72);
  });
});

describe('Epic 5 dynamic classifications', () => {
  it('uses the same regional resemblance tiers and colours as the heatmap legend', () => {
    expect(getRegionalResemblanceSummary(0.21, 0.30)).toEqual({
      colour: '#7C3AED', floor: 0.66, label: '66-100% of the regional best'
    });
    expect(getRegionalResemblanceSummary(0.15, 0.30)?.label).toBe('33-66%');
    expect(getRegionalResemblanceSummary(0.05, 0.30)?.label).toBe('under 33%');
    expect(getRegionalResemblanceSummary(0.21, null)).toBeNull();
  });

  it('uses the POI density thresholds', () => {
    expect(getPoiDescription(80, 16)).toBe('16 Commercial POIs • High density');
    expect(getPoiDescription(40, 8)).toContain('Moderate density');
    expect(getPoiDescription(39, 4)).toContain('Low density');
  });

  it('uses the overlap risk thresholds', () => {
    expect(getOverlapDescription(80, 4)).toContain('Low network overlap risk');
    expect(getOverlapDescription(40, 2)).toContain('Moderate network overlap risk');
    expect(getOverlapDescription(39, 1.9)).toContain('High network overlap risk');
  });

  it('explains heatmap scores with red, yellow, and green zones', () => {
    expect(getHeatmapDescription(80)).toContain('Red Zone');
    expect(getHeatmapDescription(40)).toContain('Yellow Zone');
    expect(getHeatmapDescription(39)).toContain('Green Zone');
  });

  it('classifies payback periods at the boundaries', () => {
    expect(getPaybackStatus(2.9)).toBe('Rapid capital recovery');
    expect(getPaybackStatus(3)).toBe('Standard capital recovery');
    expect(getPaybackStatus(5)).toBe('Standard capital recovery');
    expect(getPaybackStatus(5.1)).toBe('Long-term capital recovery');
  });

  it('formats abbreviated Indonesian revenue in Juta and Miliar', () => {
    expect(formatRevenueIdr(24_000_000)).toBe('Rp. 24 Juta');
    expect(formatRevenueIdr(8_500_000)).toBe('Rp. 8,5 Juta');
    expect(formatRevenueIdr(1_200_000_000)).toBe('Rp. 1,2 Miliar');
  });
});

describe('Epic 5 nearby station and marker selection logic', () => {
  const stations = [
    { id: 'far', name: 'Far', distanceKm: 5.1, averageDailySessions: 1, dailySessionsTrendPct: 1, monthlyRevenueIdr: 1, monthlyRevenueTrendPct: 1 },
    { id: 'second', name: 'Second', distanceKm: 2, averageDailySessions: 1, dailySessionsTrendPct: 1, monthlyRevenueIdr: 1, monthlyRevenueTrendPct: 1 },
    { id: 'first', name: 'First', distanceKm: 1, averageDailySessions: 1, dailySessionsTrendPct: 1, monthlyRevenueIdr: 1, monthlyRevenueTrendPct: 1 },
    { id: 'edge', name: 'Edge', distanceKm: 5, averageDailySessions: 1, dailySessionsTrendPct: 1, monthlyRevenueIdr: 1, monthlyRevenueTrendPct: 1 }
  ];

  it('filters to five kilometres inclusively and sorts without mutating input', () => {
    const filtered = getNearbyStationsWithinRadius(stations);
    expect(filtered.map((station) => station.id)).toEqual(['second', 'first', 'edge']);
    expect(sortStationsByDistance(filtered).map((station) => station.id)).toEqual(['first', 'second', 'edge']);
    expect(filtered[0]?.id).toBe('second');
  });

  it('resolves Optimal Sites but ignores SPKLU and POI marker IDs', () => {
    const sites = generateMockOptimalSites(jakartaViewport);
    expect(resolveOptimalSite(sites, 'mock-optimal-94')?.score).toBe(94);
    expect(resolveOptimalSite(sites, 'spklu-menteng')).toBeNull();
    expect(resolveOptimalSite(sites, 'poi-mall')).toBeNull();
  });

  it('provides stable feasibility data for every generated Optimal Site', async () => {
    const sites = generateMockOptimalSites(jakartaViewport);
    const records = await Promise.all(sites.map((site) => getSiteFeasibility(site.id)));
    expect(records.map((record) => record.optimalSiteId)).toEqual(sites.map((site) => site.id));
    expect(records.every((record) => record.locationCode.startsWith('LOC-JKT-'))).toBe(true);
  });
});

describe('the site detail preserves backend scoring inputs', () => {
  const detail = (over: Partial<PlannerCellDetailApi> = {}): PlannerCellDetailApi => ({
    cell_id: 'JBDTBK_12253', kota: 'Kota Depok', latitude: -6.4, longitude: 106.8,
    score: 0.42, rank_overall: 12, cells_total: 27219, in_scored_set: true,
    overlap_frac: 1, population: 900, poi: { total: 30 }, land_use: { residential: 0.5 },
    road_nodes: 22, road_length_m: 1200, station_count: 0, connector_count: 0,
    nearest_station_m: 2532, stations_2km: 0,
    provenance: {} as PlannerCellDetailApi['provenance'], ...over
  });

  it('keeps the API suitability band without presenting it as a legacy traffic-light zone', () => {
    const red = plannerCellToSiteFeasibility(
      detail({ suitability: 0.9975, suitability_band: 'red' }), null);
    expect(red.heatmapBand).toBe('red');
  });

  it('scores the cell on suitability when the API supplies it', () => {
    const cell = plannerCellToSiteFeasibility(
      detail({ score: 0.42, suitability: 0.9975, suitability_band: 'red' }), null);
    expect(cell.heatmapScore).toBe(100);
    // The headline follows it. The weighted score is not lost, it moves to
    // criteriaScore: two questions still have two answers, and the planner's
    // cross-check is one field away rather than gone.
    expect(cell.locationScore).toBe(100);
    expect(cell.criteriaScore).toBe(42);
  });

  it('falls back to the weighted score when no band was supplied', () => {
    const cell = plannerCellToSiteFeasibility(detail(), null);
    expect(cell.heatmapScore).toBe(42);
    expect(cell.heatmapBand).toBeNull();
  });
});

describe('the headline score is the one the map paints', () => {
  const detail = (over: Partial<PlannerCellDetailApi> = {}): PlannerCellDetailApi => ({
    cell_id: 'JBDTBK_24759', kota: 'Kota Jakarta Utara', latitude: -6.1, longitude: 106.9,
    score: 0.6518, rank_overall: 12, cells_total: 27219, in_scored_set: true,
    overlap_frac: 1, population: 900, poi: { total: 2 }, land_use: { residential: 0.5 },
    road_nodes: 22, road_length_m: 1200, station_count: 0, connector_count: 0,
    nearest_station_m: 2236, stations_2km: 0,
    suitability: 0.8492, suitability_band: 'red',
    provenance: {} as PlannerCellDetailApi['provenance'], ...over
  });

  it('shows the suitability, not the weighted criteria score', () => {
    // The card used to lead with 65 while the first breakdown row said 85, and
    // nothing on it said the two were different quantities.
    const d = plannerCellToSiteFeasibility(detail(), null);
    expect(d.locationScore).toBe(85);
    expect(calculateSiteScores(d).location).toBe(85);
  });

  it('keeps the weighted score rather than discarding it', () => {
    // Hidden on this card, not deleted: the backend still sends it, saved sites
    // still store it, and the adjustable weights behind it are a real feature.
    expect(plannerCellToSiteFeasibility(detail(), null).criteriaScore).toBe(65);
  });

  it('cannot label a red cell Low Priority', () => {
    // The contradiction this change exists to remove. Under fixed thresholds a
    // suitability of 84 sat below the 85 cut and read Low Priority while the map
    // painted the same cell red.
    const d = plannerCellToSiteFeasibility(detail({ suitability: 0.84 }), null);
    expect(getLocationPriority(d.locationScore ?? 0, d.heatmapBand)).toBe('High Priority');
  });

  it('follows the band through every colour', () => {
    for (const [band, label] of [['red', 'High Priority'], ['yellow', 'Moderate Priority'],
                                 ['green', 'Low Priority']] as const) {
      expect(getLocationPriority(50, band)).toBe(label);
    }
  });

  it('falls back to the weighted score when no suitability was returned', () => {
    // Any deployment without the utilisation artifact. The old thresholds still
    // apply there, because there is no band to follow.
    const d = plannerCellToSiteFeasibility(
      detail({ suitability: null, suitability_band: null }), null);
    expect(d.locationScore).toBe(65);
    expect(getLocationPriority(d.locationScore ?? 0, d.heatmapBand)).toBe('Low Priority');
  });
});

it('carries the band through to the components, not just the helpers', () => {
  // The gap this test exists for: getLocationPriority and getHeatmapDescription
  // both accept a band, but every call site passed only the score, so the band
  // logic never ran. A helper that supports something nothing supplies is not
  // wired.
  const d = plannerCellToSiteFeasibility({
    cell_id: 'JBDTBK_24759', kota: 'Kota Jakarta Utara', latitude: -6.1, longitude: 106.9,
    score: 0.6518, rank_overall: 12, cells_total: 27219, in_scored_set: true,
    overlap_frac: 1, population: 900, poi: { total: 2 }, land_use: { residential: 0.5 },
    road_nodes: 22, road_length_m: 1200, station_count: 0, connector_count: 0,
    nearest_station_m: 2236, stations_2km: 0, suitability: 0.8492, suitability_band: 'red',
    provenance: {} as PlannerCellDetailApi['provenance']
  }, null);
  expect(calculateSiteScores(d).band).toBe('red');
});
