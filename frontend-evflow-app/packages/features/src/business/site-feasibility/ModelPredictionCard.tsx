import { StyleSheet, Text, View } from 'react-native';
import type { PlannerModelInfoApi } from '@evflow/shared';

type Props = {
  probability: number | null;
  model: PlannerModelInfoApi | null;
  interpretation: string | null;
  loading: boolean;
  error: string | null;
};

/**
 * The trained model's probability, shown with the caveat that has to travel
 * with it.
 *
 * The model predicts P(this cell contains a station), learned from the existing
 * network. 1,080 of the 1,236 stations it learned from are PLN placements that
 * follow PLN offices and policy targets. Measured on the grid, its 500
 * highest-probability cells ALL already have a station, against a base rate of
 * 3.3%. So a high number means "resembles somewhere PLN builds", which is not
 * the same claim as "good site".
 *
 * That is why the interpretation text from the API is rendered in full rather
 * than summarised into a label. A planner reading a bare percentage has no way
 * to know which of the two questions it answered, and the number looks
 * authoritative either way.
 */
export function ModelPredictionCard({ probability, model, interpretation, loading, error }: Props) {
  if (loading) {
    return (
      <View style={styles.card}>
        <Text style={styles.label}>MODEL PREDICTION</Text>
        <Text style={styles.muted}>Loading…</Text>
      </View>
    );
  }

  if (error || probability === null) {
    return (
      <View style={styles.card}>
        <Text style={styles.label}>MODEL PREDICTION</Text>
        <Text style={styles.muted}>{error ?? 'No trained model is available for this cell.'}</Text>
      </View>
    );
  }

  const pct = Math.round(probability * 1000) / 10;

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.label}>MODEL PREDICTION</Text>
        {model ? (
          // The leave-one-area-out figure, not the random-split one. The
          // random split scores 0.927 and means far less: neighbouring cells
          // land on both sides of it, so the model recalls nearby answers.
          <Text style={styles.badge}>AUC {model.loco_auc.toFixed(3)}</Text>
        ) : null}
      </View>

      <View style={styles.valueRow}>
        <Text style={styles.value}>{pct}</Text>
        <Text style={styles.unit}>% resemblance</Text>
      </View>

      <Text style={styles.caption}>
        Probability this cell resembles one that already has a station
      </Text>

      {interpretation ? <Text style={styles.caveat}>{interpretation}</Text> : null}

      {model ? (
        <Text style={styles.provenance}>
          {model.label} · trained on {model.n_samples.toLocaleString()} cells
          ({model.n_positive.toLocaleString()} with a station) · {model.n_features} features
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    backgroundColor: '#E8F1F2',
    borderRadius: 4,
    color: '#00565F',
    fontSize: 11,
    fontWeight: '700',
    overflow: 'hidden',
    paddingHorizontal: 6,
    paddingVertical: 2
  },
  card: {
    backgroundColor: '#F7F9FA',
    borderColor: '#DDE5E7',
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14
  },
  // Deliberately not a warning colour. This is not an error state; it is the
  // normal, permanent meaning of the number above it.
  caveat: {
    color: '#55656A',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 10
  },
  caption: { color: '#55656A', fontSize: 12, marginTop: 2 },
  headerRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  label: { color: '#8A979B', fontSize: 11, fontWeight: '700', letterSpacing: 0.6 },
  muted: { color: '#8A979B', fontSize: 12, marginTop: 6 },
  provenance: {
    borderTopColor: '#E4EAEC',
    borderTopWidth: 1,
    color: '#8A979B',
    fontSize: 10,
    lineHeight: 14,
    marginTop: 10,
    paddingTop: 8
  },
  unit: { color: '#55656A', fontSize: 13, marginBottom: 4, marginLeft: 4 },
  value: { color: '#00565F', fontSize: 30, fontWeight: '800' },
  valueRow: { alignItems: 'flex-end', flexDirection: 'row', marginTop: 8 }
});
