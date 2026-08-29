export type RoadType = 'primary' | 'secondary' | 'local';

export type FinancialProjection = {
  sessionsPerDay: number;
  energyPerDayKwh: number;
  monthlyRevenueIdr: number;
  paybackYears: number | null;
  breaksEven: boolean;
  utilisation?: number;
  capacitySessionsPerDay?: number;
  demandBasis?: string;
  costBasis?: string;
  inputSources?: Record<string, string>;
  projectionKind: 'backend' | 'mock';
};

export type NearbyStationBenchmark = {
  id: string;
  name: string;
  distanceKm: number;
  /**
   * Real fields from the benchmark endpoint, kept apart from the prototype
   * performance numbers below. The connection graph draws only these: sessions
   * and revenue are generated, and putting them on a diagram of the competitive
   * landscape would state something nobody measured.
   */
  operator?: string | null;
  powerKw?: number | null;
  speedTier?: string | null;
  latitude?: number;
  longitude?: number;
  averageDailySessions: number;
  dailySessionsTrendPct: number;
  monthlyRevenueIdr: number;
  monthlyRevenueTrendPct: number;
  availableConnectors?: number;
  totalConnectors?: number;
};

export type SiteFeasibilityData = {
  optimalSiteId: string;
  locationCode: string;
  locationName: string;
  latitude: number;
  longitude: number;
  /**
   * The number the MAP paints, and therefore the headline on this card.
   *
   * It used to be the weighted four-criteria score while the first breakdown row
   * showed suitability, so the card could read "Low Priority" above "Red Zone"
   * with nothing saying the two were different quantities.
   */
  locationScore?: number;
  /**
   * The weighted four-criteria score, kept but not displayed.
   *
   * The backend still returns it, saved sites still store it, and the adjustable
   * weights behind it remain a real planner feature. Hidden on this card rather
   * than removed, so the second opinion is one line away rather than gone.
   */
  criteriaScore: number | null;
  heatmapScore: number;
  /**
   * The band the MAP painted this cell, straight from the API.
   *
   * Carried rather than re-derived because the card used to decide the zone
   * itself, from a threshold on a different number, so "Located in a Red Demand
   * Zone" could sit over a cell the map had painted green. Null when the API
   * supplied no band, in which case the old threshold still applies -- it is
   * only wrong when a real band exists to contradict it.
   */
  heatmapBand: string | null;
  commercialPoiCount: number;
  nearestSpkluDistanceKm: number;
  roadType: RoadType;
  residentialPoints: number;
  financial: FinancialProjection | null;
  nearbyStations: NearbyStationBenchmark[];
};

export type SiteFeasibilityTab = 'feasibility' | 'financial' | 'nearby';

export type SiteFeasibilityScores = {
  heatmap: number;
  poi: number;
  overlap: number;
  activity: number;
  location: number;
  /** The band the map painted, so the labels below cannot contradict the colour. */
  band: string | null;
};
