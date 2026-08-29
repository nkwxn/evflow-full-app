import type { OptimalSite } from '../demandHeatmap';
import { resemblanceBand } from '../site-prediction/areaPrediction';
import type {
  NearbyStationBenchmark,
  RoadType,
  SiteFeasibilityData,
  SiteFeasibilityScores
} from './siteFeasibilityTypes';

const trafficPoints: Record<RoadType, number> = { primary: 50, secondary: 35, local: 15 };

export function calculatePoiScore(commercialPoiCount: number) {
  return Math.min(Math.max(commercialPoiCount, 0) / 20 * 100, 100);
}

export function calculateOverlapScore(nearestSpkluDistanceKm: number) {
  return Math.min(Math.max(nearestSpkluDistanceKm, 0) / 5 * 100, 100);
}

export function calculateActivityScore(roadType: RoadType, residentialPoints: number) {
  return Math.min(trafficPoints[roadType] + Math.min(Math.max(residentialPoints, 0), 50), 100);
}

export function calculateLocationScore(heatmap: number, overlap: number, poi: number, activity: number) {
  return Math.round(0.4 * heatmap + 0.3 * overlap + 0.15 * poi + 0.15 * activity);
}

export function calculateSiteScores(data: SiteFeasibilityData): SiteFeasibilityScores {
  const poi = calculatePoiScore(data.commercialPoiCount);
  const overlap = calculateOverlapScore(data.nearestSpkluDistanceKm);
  const activity = calculateActivityScore(data.roadType, data.residentialPoints);
  return {
    heatmap: data.heatmapScore,
    poi,
    overlap,
    activity,
    location: data.locationScore ?? calculateLocationScore(data.heatmapScore, overlap, poi, activity),
    band: data.heatmapBand ?? null
  };
}

/**
 * Priority, taken from the band the map painted wherever there is one.
 *
 * Fixed cuts at 85 and 70 belonged to a different score's distribution. Against
 * suitability they disagreed with the map: the red band starts at 83.4, so a
 * cell could be painted red and still read Low Priority. Following the band
 * makes that contradiction impossible rather than unlikely, and it stays true
 * after a retrain because the floors are recomputed per response.
 *
 * The numeric cuts remain for the case with no band, which is any deployment
 * without the utilisation artifact.
 */
export function getLocationPriority(score: number, band?: string | null) {
  if (band === 'red') return 'High Priority';
  if (band === 'yellow') return 'Moderate Priority';
  if (band === 'green') return 'Low Priority';
  return score >= 85 ? 'High Priority' : score >= 70 ? 'Moderate Priority' : 'Low Priority';
}

/**
 * The zone, from the map's own band where there is one.
 *
 * `band` wins over `score` whenever it is present. The two rules disagreed on
 * every cell between their thresholds, and the card is the place a planner reads
 * the claim as a sentence rather than a colour, so it is the place the
 * disagreement did the most damage.
 */
export function getRegionalResemblanceSummary(probability: number | null, ceiling: number | null) {
  if (probability === null) return null;
  return resemblanceBand(probability, ceiling);
}

export function getHeatmapDescription(score: number, band?: string | null) {
  switch (band ?? zoneFromScore(score)) {
    case 'red':
      return 'Red Zone • Top 10% of Jabodetabek, with no station within 2 km';
    case 'yellow':
      return 'Yellow Zone • Above the regional median; worth watching';
    default:
      // Never "low demand": a green cell in Sudirman predicts among the highest
      // utilisation in the region and is green because 38 stations already sit
      // within 2 km of it. Saying "low demand" there would be false.
      return 'Green Zone • Lower half of the region, or already well served';
  }
}

/** The pre-band rule, kept for responses that carry no band. */
function zoneFromScore(score: number) {
  return score >= 80 ? 'red' : score >= 40 ? 'yellow' : 'green';
}

export function getPoiSummary(score: number) {
  return score >= 70 ? 'Strong Commercial Activity' : 'Limited Commercial Activity';
}

export function getPoiDescription(score: number, count: number) {
  const density = score >= 80 ? 'High density' : score >= 40 ? 'Moderate density' : 'Low density';
  return `${count} Commercial POIs • ${density}`;
}

export function getOverlapSummary(score: number) {
  return score >= 70 ? 'Low Network Overlap' : 'High Network Overlap';
}

export function getOverlapDescription(score: number, distanceKm: number) {
  const risk = score >= 80 ? 'Low' : score >= 40 ? 'Moderate' : 'High';
  return `Nearest SPKLU ${distanceKm.toFixed(1)} km away • ${risk} network overlap risk`;
}

export function getActivityDescription(roadType: RoadType, residentialPoints: number) {
  const traffic = roadType === 'primary' ? 'Heavy traffic volume' : roadType === 'secondary' ? 'Moderate traffic flow' : 'Local traffic only';
  const residential = residentialPoints >= 40 ? 'High-density residential' : residentialPoints >= 20 ? 'Moderate residential zone' : 'Low-density residential';
  return `${traffic} • ${residential}`;
}

export function getPaybackStatus(paybackYears: number) {
  return paybackYears < 3 ? 'Rapid capital recovery' : paybackYears <= 5 ? 'Standard capital recovery' : 'Long-term capital recovery';
}

export function formatRevenueIdr(value: number) {
  if (value >= 1_000_000_000) return `Rp. ${formatCompactIdr(value / 1_000_000_000)} Miliar`;
  if (value >= 1_000_000) return `Rp. ${formatCompactIdr(value / 1_000_000)} Juta`;
  return `Rp. ${new Intl.NumberFormat('id-ID').format(value)}`;
}

function formatCompactIdr(value: number) {
  return new Intl.NumberFormat('id-ID', { maximumFractionDigits: 1 }).format(value);
}

export function getNearbyStationsWithinRadius(stations: NearbyStationBenchmark[], radiusKm = 5) {
  return stations.filter((station) => station.distanceKm <= radiusKm);
}

export function sortStationsByDistance(stations: NearbyStationBenchmark[]) {
  return [...stations].sort((left, right) => left.distanceKm - right.distanceKm);
}

export function resolveOptimalSite(sites: OptimalSite[], markerId: string) {
  return sites.find((site) => site.id === markerId) ?? null;
}
