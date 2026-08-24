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
  locationScore?: number;
  heatmapScore: number;
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
};
