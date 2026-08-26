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
 * The candidate site and what it would be competing with, as an ordered list.
 *
 * WHY A LIST AND NOT THE DIAGRAM IT USED TO BE
 *
 * There was a React Flow sibling for web that arranged competitors in a ring,
 * radius tracking real distance, so "am I hemmed in" could be read at a glance.
 * On a phone that ring collapses: ten 150 px nodes overlap inside a 320 px box,
 * labels sit on top of each other, and the thing it was drawn to communicate is
 * the first thing lost. This app renders on phone browsers as well as Expo, so
 * the diagram was failing exactly where it was needed most.
 *
 * The list keeps every fact the diagram carried -- competitor, operator, power,
 * connectors, distance, pressure band down the left edge -- and pressureSummary
 * states the crowding in words above it ("2 SPKLU within 1 km ... closest is
 * 854 m"), which is the sentence the ring existed to draw.
 *
 * It reads from buildGraph rather than the raw stations because that is where
 * ordering and pressure banding live, and both must stay identical to whatever
 * else consumes them.
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
