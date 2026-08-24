import { StyleSheet, Text, View } from 'react-native';
import type { NearbyStationBenchmark } from '../site-feasibility/siteFeasibilityTypes';
import {
  buildGraph, formatDistance, pressureSummary, type Pressure
} from './competitiveLandscape';

type Props = {
  site: { id: string; label: string; score: number };
  stations: NearbyStationBenchmark[];
};

/**
 * The native half of the competitive landscape view.
 *
 * React Flow is DOM-based, so on Expo the same facts are laid out as an ordered
 * list rather than a diagram. It reads from buildGraph, not from the raw
 * stations, so both platforms show the same competitors in the same order with
 * the same distances and the same pressure banding: a difference between them
 * would be a difference nobody could explain.
 */
export function SiteConnectionGraph({ site, stations }: Props) {
  const { nodes } = buildGraph(site, stations);
  const competitors = nodes.filter((n) => n.kind === 'station');

  return (
    <View>
      <Text style={styles.label}>COMPETITIVE LANDSCAPE</Text>
      <Text style={styles.summary}>{pressureSummary(stations)}</Text>

      <View style={styles.siteCard}>
        <Text style={styles.siteName}>{site.label}</Text>
        <Text style={styles.siteScore}>Viability {site.score}</Text>
      </View>

      {competitors.map((n) => {
        const station = stations.find((s) => s.id === n.id);
        return (
          <View key={n.id} style={[styles.row, { borderLeftColor: BORDER[n.pressure ?? 'low'] }]}>
            <View style={styles.rowText}>
              <Text style={styles.stationName}>{n.label}</Text>
              {n.sublabel ? <Text style={styles.stationMeta}>{n.sublabel}</Text> : null}
            </View>
            <Text style={styles.distance}>
              {station ? formatDistance(station.distanceKm) : ''}
            </Text>
          </View>
        );
      })}

      <Text style={styles.provenance}>
        Distance, operator, power and connector count come from the station records.
        Sessions and revenue are not shown here: those figures are generated.
      </Text>
    </View>
  );
}

const BORDER: Record<Pressure, string> = {
  high: '#EF4444', moderate: '#F59E0B', low: '#10B981'
};

const styles = StyleSheet.create({
  distance: { color: '#26383D', fontSize: 12, fontWeight: '700' },
  label: { color: '#8A979B', fontSize: 11, fontWeight: '700', letterSpacing: 0.6 },
  provenance: {
    borderTopColor: '#E4EAEC', borderTopWidth: 1, color: '#8A979B', fontSize: 10,
    lineHeight: 14, marginTop: 10, paddingTop: 8
  },
  row: {
    alignItems: 'center', backgroundColor: '#F7F9FA', borderLeftWidth: 3, borderRadius: 6,
    flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, padding: 10
  },
  rowText: { flex: 1, paddingRight: 8 },
  siteCard: { backgroundColor: '#00565F', borderRadius: 8, marginTop: 10, padding: 10 },
  siteName: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  siteScore: { color: '#BFE3E8', fontSize: 11, marginTop: 2 },
  stationMeta: { color: '#55656A', fontSize: 10, marginTop: 2 },
  stationName: { color: '#26383D', fontSize: 12, fontWeight: '600' },
  summary: { color: '#55656A', fontSize: 12, marginBottom: 2, marginTop: 4 }
});
