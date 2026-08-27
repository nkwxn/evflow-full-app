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
 * network, 87% of which is PLN: 1,038 of the 1,192 stations inside the scored
 * grid, measured 2026-08-26. Measured on the grid, its 500
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
        <Text style={styles.muted}>{error ?? 'No trained model is available for this place.'}</Text>
      </View>
    );
  }

  const pct = Math.round(probability * 1000) / 10;

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.label}>MODEL PREDICTION</Text>
        {model ? (
          // Was "AUC 0.807". It is the leave-one-area-out figure, not the
          // random split, which scores 0.927 and means far less because
          // neighbouring cells land on both sides of it. None of that is
          // actionable for a planner, so the number is labelled in words and
          // explained at the foot of the card.
          <Text style={styles.badge}>Reliability {model.loco_auc.toFixed(2)}</Text>
        ) : null}
      </View>

      <View style={styles.valueRow}>
        <Text style={styles.value}>{pct}</Text>
        <Text style={styles.unit}>% like an existing charger site</Text>
      </View>

      <Text style={styles.caption}>
        How closely this place matches the ones that already have a charger
      </Text>

      {/*
        The API's `interpretation` names both models and the column behind the
        number. It stays in the response, and this card says the one thing a
        planner has to take from it instead.
      */}
      <Text style={styles.caveat}>
        A high figure is not a recommendation. Most chargers in Jabodetabek today are
        PLN&rsquo;s, so this mostly says how much the place looks like somewhere PLN has
        already built — useful background when you are weighing a site, but not a reason
        to pick it. The colour on the map is what ranks places against each other.
      </Text>

      {model ? (
        <Text style={styles.provenance}>
          Compared against {model.n_samples.toLocaleString()} places across Jabodetabek,
          {' '}{model.n_positive.toLocaleString()} of which have a charger today.
          {' '}Reliability {model.loco_auc.toFixed(2)} out of 1.00, measured by holding back
          whole districts the model had never seen — good, not perfect.
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
