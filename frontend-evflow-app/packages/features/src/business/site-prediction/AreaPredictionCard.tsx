import { StyleSheet, Text, View } from 'react-native';
import type {
  PlannerAreaDistributionApi, PlannerModelInfoApi, PlannerUtilisationInfoApi
} from '@evflow/shared';
import {
  BUILT_COLOUR,
  distributionSummary,
  drawTruncationNote,
  resemblanceCaption,
  truncationWarning
} from './areaPrediction';

type Props = {
  distribution: PlannerAreaDistributionApi | null;
  /** Cells drawn on the map. Below what was scored when the draw limit trimmed them. */
  drawnCells: number;
  radiusKm: number;
  model: PlannerModelInfoApi | null;
  /** The prescriptive model. Null when no utilisation artifact is loaded. */
  utilisationModel: PlannerUtilisationInfoApi | null;
  interpretation: string | null;
  loading: boolean;
  error: string | null;
};

/**
 * What the model says about the circle the planner picked.
 *
 * THIS IS NOT A SITING RECOMMENDATION, AND THE CARD IS BUILT SO IT CANNOT BE
 * READ AS ONE.
 *
 * The model is descriptive: it learned which cells CONTAIN a station, from a
 * network that is 1,080 PLN placements out of 1,236. Measured across the whole
 * grid, its 500 highest-probability cells are 100% cells that already have one,
 * and of the 26,334 cells with none, the highest probability is 0.305 with not
 * one above 0.5.
 *
 * An earlier version of this card led with "N cells worth a look", counting
 * cells above 0.5. On the real grid that count was almost entirely cells that
 * already had a station, presented as candidates. What replaced it:
 *
 *   - the headline is how many cells here have NO station, the opportunity space
 *   - the resemblance figure covers only those cells, never the built ones
 *   - it carries a caption giving it a scale, because 0.26 reads as "poor" to
 *     anyone who does not know it is near the ceiling for unbuilt cells
 *   - cells that are already built are named, not quietly folded into the total
 *
 * The weighted criteria score, not this, is what answers "where should we
 * build". This answers "how much does this resemble the places that get built
 * on", which is worth reading beside it and never instead of it.
 */
export function AreaPredictionCard({
  distribution, drawnCells, radiusKm, model, utilisationModel, interpretation, loading, error
}: Props) {
  if (loading) {
    return (
      <View style={styles.card}>
        <Text style={styles.label}>MODEL CHECK · {radiusKm} KM</Text>
        <Text style={styles.muted}>Scoring this area…</Text>
      </View>
    );
  }

  if (error || !distribution) {
    return (
      <View style={styles.card}>
        <Text style={styles.label}>MODEL CHECK</Text>
        <Text style={styles.muted}>{error ?? 'Tap the map to choose a place to analyse.'}</Text>
      </View>
    );
  }

  const clipped = truncationWarning(distribution);
  const partiallyDrawn = drawTruncationNote(drawnCells, distribution.cells_predicted);
  const { max_probability: best, median_probability: mid } = distribution;

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.label}>MODEL CHECK · {radiusKm} KM</Text>
        {model ? (
          // The leave-one-area-out figure. The random split scores higher and
          // means less: neighbouring cells land on both sides of it.
          <Text style={styles.badge}>AUC {model.loco_auc.toFixed(3)}</Text>
        ) : null}
      </View>

      <View style={styles.valueRow}>
        <Text style={styles.value}>{distribution.cells_without_station.toLocaleString()}</Text>
        <Text style={styles.unit}>cells with no station yet</Text>
      </View>
      <Text style={styles.caption}>{distributionSummary(distribution)}</Text>

      {distribution.cells_with_station > 0 ? (
        <View style={styles.builtRow}>
          <View style={styles.builtSwatch} />
          <Text style={styles.builtText}>
            {distribution.cells_with_station.toLocaleString()} already built, shown in slate.
            These are the cells the model scores highest, which is why they are not on the
            resemblance scale.
          </Text>
        </View>
      ) : null}

      {utilisationModel && distribution.median_sessions_per_connector_day !== null ? (
        <>
          <View style={styles.statRow}>
            <Stat
              label="BUSIEST UNBUILT"
              value={distribution.max_sessions_per_connector_day}
              digits={1}
            />
            <Stat
              label="TYPICAL UNBUILT"
              value={distribution.median_sessions_per_connector_day}
              digits={1}
            />
          </View>
          <Text style={styles.scaleNote}>
            Simulated sessions per connector per day, every cell scored at the same{' '}
            {formatSpec(utilisationModel.reference_spec)} site so what differs is the place
            and not the hardware. A SCENARIO recovered from the simulation&rsquo;s own demand
            assumption, not a forecast. Across the whole grid this model separates cells by
            about 1.7x, so read two cells as close unless they are far apart.
          </Text>
        </>
      ) : null}

      {best !== null ? (
        <>
          <View style={styles.statRow}>
            <Stat label="BEST UNBUILT" value={best} />
            <Stat label="MEDIAN UNBUILT" value={mid} />
          </View>
          <Text style={styles.scaleNote}>
            {resemblanceCaption(best, distribution.resemblance_ceiling)}
          </Text>
        </>
      ) : null}

      {clipped ? <Text style={styles.warning}>{clipped}</Text> : null}
      {partiallyDrawn ? <Text style={styles.warning}>{partiallyDrawn}</Text> : null}
      {interpretation ? <Text style={styles.caveat}>{interpretation}</Text> : null}

      {model ? (
        <Text style={styles.provenance}>
          Resemblance: {model.label} · trained on {model.n_samples.toLocaleString()} cells
          ({model.n_positive.toLocaleString()} with a station) · {model.n_features} features
          · scored on request, not precomputed
        </Text>
      ) : null}

      {/*
        The prescriptive model gets its own line rather than sharing the one
        above. They were trained on different targets over different windows, and
        a single provenance line describing one of them read as if it described
        the whole card — which is exactly how the screen came to say "station
        presence (descriptive)" underneath a utilisation number.
      */}
      {utilisationModel ? (
        <Text style={styles.provenance}>
          Utilisation: {utilisationModel.label} · {utilisationModel.n_samples.toLocaleString()}{' '}
          cells over {utilisationModel.window_days}{' '}
          {utilisationModel.window_days === 1 ? 'day' : 'days'} of demand-weighted simulation
          · dose-response {utilisationModel.dose_response.toFixed(2)}x
          {utilisationModel.counting_noise_pct !== null
            ? ` · ±${Math.round(utilisationModel.counting_noise_pct)}% counting noise`
            : ''}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * Reference hardware as a phrase a planner reads, e.g. "2-connector, 22 kW".
 *
 * The spec travels with every response because moving it moves every number at
 * once: charger power carries most of what decides how many sessions a connector
 * turns over. Printing it beside the figure is what stops two screenshots taken
 * at different specs from being compared as if they were the same measurement.
 */
function formatSpec(spec: Record<string, number>): string {
  const connectors = spec.connectors;
  const kw = spec.avg_kw;
  if (connectors === undefined || kw === undefined) return 'reference';
  return `${connectors.toFixed(0)}-connector, ${kw.toFixed(0)} kW`;
}

function Stat({ label, value, digits = 2 }:
  { label: string; value: number | null; digits?: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statLabel}>{label}</Text>
      {/* Two decimals by default, and never a percentage: a percentage invites
          comparison with the weighted criteria score, which is a different
          quantity entirely. Utilisation passes digits=1 because a tenth of a
          session per connector per day is already past what a 3-day window
          with ~19% counting noise can resolve. */}
      <Text style={styles.statValue}>{value === null ? '—' : value.toFixed(digits)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    backgroundColor: '#EDE9FE', borderRadius: 4, color: '#5B21B6', fontSize: 11,
    fontWeight: '700', overflow: 'hidden', paddingHorizontal: 6, paddingVertical: 2
  },
  builtRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  builtSwatch: {
    backgroundColor: BUILT_COLOUR, borderRadius: 3, height: 12, marginTop: 2, width: 12
  },
  builtText: { color: '#55656A', flex: 1, fontSize: 11, lineHeight: 16 },
  caption: { color: '#55656A', fontSize: 12, marginTop: 2 },
  card: {
    backgroundColor: '#F7F9FA', borderColor: '#DDE5E7', borderRadius: 10, borderWidth: 1,
    marginBottom: 12, padding: 14
  },
  // Not a warning colour. This is the permanent meaning of the numbers above it.
  caveat: { color: '#55656A', fontSize: 11, lineHeight: 16, marginTop: 10 },
  headerRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  label: { color: '#8A979B', fontSize: 11, fontWeight: '700', letterSpacing: 0.6 },
  muted: { color: '#8A979B', fontSize: 12, marginTop: 6 },
  provenance: {
    borderTopColor: '#E4EAEC', borderTopWidth: 1, color: '#8A979B', fontSize: 10,
    lineHeight: 14, marginTop: 10, paddingTop: 8
  },
  scaleNote: { color: '#55656A', fontSize: 11, lineHeight: 16, marginTop: 8 },
  stat: { flex: 1 },
  statLabel: { color: '#8A979B', fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  statRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  statValue: { color: '#26383D', fontSize: 18, fontWeight: '700', marginTop: 2 },
  unit: { color: '#55656A', fontSize: 13, marginBottom: 4, marginLeft: 6 },
  value: { color: '#5B21B6', fontSize: 30, fontWeight: '800' },
  valueRow: { alignItems: 'flex-end', flexDirection: 'row', marginTop: 8 },
  // This one IS a warning: a clipped area looks exactly like a complete one.
  warning: { color: '#B45309', fontSize: 11, lineHeight: 16, marginTop: 10 }
});
