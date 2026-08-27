import { StyleSheet, Text, View } from 'react-native';
import type {
  PlannerAreaDistributionApi, PlannerModelInfoApi, PlannerUtilisationInfoApi
} from '@evflow/shared';
import {
  BUILT_COLOUR,
  distributionSummary,
  drawTruncationNote,
  resemblanceCaption,
  suitabilityKeyNote,
  suitabilityKeyRows,
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
 * network 87% operated by PLN, 1,038 of 1,192. Measured across the whole
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
  const keyRows = suitabilityKeyRows(distribution);

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.label}>MODEL CHECK · {radiusKm} KM</Text>
        {model ? (
          // Was "AUC 0.807". AUC is a modelling metric, and a planner cannot act
          // on it or tell a good one from a bad one. The number is kept because
          // hiding how well the model does would be worse, but it is labelled in
          // words and explained at the bottom of the card.
          <Text style={styles.badge}>Reliability {model.loco_auc.toFixed(2)}</Text>
        ) : null}
      </View>

      <View style={styles.valueRow}>
        <Text style={styles.value}>{distribution.cells_without_station.toLocaleString()}</Text>
        <Text style={styles.unit}>places here with no charger yet</Text>
      </View>
      <Text style={styles.caption}>{distributionSummary(distribution)}</Text>

      {keyRows.length > 0 ? (
        <View style={styles.keyBlock}>
          <Text style={styles.label}>WHAT THE COLOURS MEAN</Text>
          {keyRows.map((row) => (
            <View key={row.colour} style={styles.keyRow}>
              <View style={[styles.keySwatch, { backgroundColor: row.colour }]} />
              <Text style={styles.keyLabel}>{row.label}</Text>
              <Text style={styles.keyCount}>
                {row.count === null ? '—' : row.count.toLocaleString()}
              </Text>
            </View>
          ))}
          <Text style={styles.scaleNote}>{suitabilityKeyNote(distribution.suitability_scale)}</Text>
        </View>
      ) : distribution.cells_with_station > 0 ? (
        // No scale, so no bands to key. Grey still needs explaining, because it
        // is on the map either way.
        <View style={styles.keyRow}>
          <View style={[styles.keySwatch, { backgroundColor: BUILT_COLOUR }]} />
          <Text style={styles.keyLabel}>
            {distribution.cells_with_station.toLocaleString()} places here already have a
            charger. They are greyed out rather than ranked — somewhere already built is not
            an opportunity.
          </Text>
        </View>
      ) : null}

      {utilisationModel && distribution.median_sessions_per_connector_day !== null ? (
        <>
          <View style={styles.statRow}>
            <Stat
              label="BUSIEST OPEN PLACE"
              value={distribution.max_sessions_per_connector_day}
              digits={1}
            />
            <Stat
              label="TYPICAL OPEN PLACE"
              value={distribution.median_sessions_per_connector_day}
              digits={1}
            />
          </View>
          <Text style={styles.scaleNote}>
            Charging sessions per connector per day. Every place is compared as if you built
            the same {formatSpec(utilisationModel.reference_spec)} site there, so what differs
            is the location and not the equipment. These come from a simulation, not from real
            charging records — treat them as a planning scenario rather than a forecast. Busiest
            and quietest across Jabodetabek differ by only about 1.7x, so two places within a
            few tenths of each other are effectively tied.
          </Text>
        </>
      ) : null}

      {best !== null ? (
        <>
          <View style={styles.statRow}>
            <Stat label="MOST LIKE AN EXISTING SITE" value={best} />
            <Stat label="TYPICAL HERE" value={mid} />
          </View>
          <Text style={styles.scaleNote}>
            {resemblanceCaption(best, distribution.resemblance_ceiling)}
          </Text>
        </>
      ) : null}

      {clipped ? <Text style={styles.warning}>{clipped}</Text> : null}
      {partiallyDrawn ? <Text style={styles.warning}>{partiallyDrawn}</Text> : null}

      {/*
        The API's `interpretation` string is written for whoever maintains the
        models — it names the two models, the migrations behind the simulation
        and the column `sessions_per_connector_day`. It stays in the response,
        because that is the right place for it, and is replaced here by the two
        things a planner has to know: the numbers are simulated, and looking like
        an existing site is not a recommendation.
      */}
      <Text style={styles.caveat}>
        Two things to keep in mind. The session figures come from a simulation of
        charging behaviour, not from real charging records, so they show how places
        compare rather than what any of them will actually earn. And most chargers in
        Jabodetabek today are PLN&rsquo;s, so &ldquo;looks like an existing site&rdquo;
        largely means &ldquo;looks like somewhere PLN has built&rdquo; — useful context,
        but not a reason to build.
      </Text>

      {model || utilisationModel ? (
        <Text style={styles.provenance}>
          {model
            ? `Scored against ${model.n_samples.toLocaleString()} places across Jabodetabek, `
              + `${model.n_positive.toLocaleString()} of which have a charger today. `
              + `Reliability ${model.loco_auc.toFixed(2)} out of 1.00, measured by holding back `
              + 'whole districts the model had never seen — good, not perfect. '
            : ''}
          {utilisationModel
            ? `Demand figures come from ${utilisationModel.window_days} `
              + `${utilisationModel.window_days === 1 ? 'day' : 'days'} of simulated charging. `
              + 'Nothing here is precomputed; every number is worked out when you ask for it.'
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
  keyBlock: {
    borderTopColor: '#E4EAEC', borderTopWidth: 1, marginTop: 12, paddingTop: 10
  },
  keyCount: { color: '#26383D', fontSize: 11, fontWeight: '700' },
  keyLabel: { color: '#55656A', flex: 1, fontSize: 11, lineHeight: 16 },
  keyRow: { alignItems: 'center', flexDirection: 'row', gap: 8, marginTop: 6 },
  keySwatch: { borderRadius: 3, height: 12, width: 12 },
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
