import { useEffect, useState } from 'react';
import { View, Text, Pressable, ScrollView, Image, type ImageSourcePropType } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { chargingFlowStyles as styles } from '@evflow/ui';
import { fetchChargingSession, type ChargingSessionApiResponse } from '@evflow/shared';
import { ChargingFlowIcon } from './components/ChargingFlowIcon';
import paymentCompletePng from '../assets/images/payment-complete.png';
import carPlugInPng from '../assets/images/car-plug-in.png';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { ChargingFlowHeader } from './components/ChargingFlowHeader';

export function TransactionSuccessScreen() {
  const router = useRouter();
  const { sessionId } = useLocalSearchParams<{ sessionId?: string | string[] }>();
  const insets = useAppSafeAreaInsets();
  const [isPluggedIn, setIsPluggedIn] = useState(false);
  const [session, setSession] = useState<ChargingSessionApiResponse | null>(null);

  const sessionIdValue = typeof sessionId === 'string' && sessionId ? sessionId : null;

  useEffect(() => {
    if (!sessionIdValue) {
      return;
    }

    let alive = true;
    fetchChargingSession(sessionIdValue)
      .then((response) => {
        if (alive) setSession(response);
      })
      .catch(() => {
        // Empty receipt state below matches a missing session; the flow can
        // still proceed into the simulated status screen.
      });

    return () => {
      alive = false;
    };
  }, [sessionIdValue]);

  useEffect(() => {
    const pluggedInTimer = setTimeout(() => {
      setIsPluggedIn(true);
    }, 5000);

    return () => {
      clearTimeout(pluggedInTimer);
    };
  }, []);

  const amountPaid = session?.deposit_idr ?? 0;
  const referenceNo = session?.id ?? '—';
  const createdAt = session?.created_at;
  const dateTime = createdAt
    ? `${new Date(createdAt).toLocaleString('id-ID', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta'
      })} WIB`
    : '—';

  return (
    <View style={styles.page}>
      <ChargingFlowHeader
        title="Transaction Success"
        onBack={() => router.back()}
      />

      <ScrollView
        style={styles.scrollBody}
        contentContainerStyle={[styles.content, { paddingBottom: 40 + insets.bottom, paddingLeft: 24 + insets.left, paddingRight: 24 + insets.right }]}
        scrollIndicatorInsets={{ bottom: insets.bottom, left: insets.left, right: insets.right }}
      >
        <View style={styles.successIconWrap}>
          <Image source={paymentCompletePng as unknown as ImageSourcePropType} style={{ width: 80, height: 80 }} />
        </View>

        <View>
          <Text style={styles.successTitle}>Payment Completed</Text>
          <Text style={styles.successSubtitle}>Your payment has been processed successfully.</Text>
        </View>

        <View style={styles.referenceCard}>
          <View style={styles.referenceRow}>
            <Text style={styles.referenceLabel}>Reference No.</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={styles.referenceValue} numberOfLines={1}>{referenceNo}</Text>
              <ChargingFlowIcon name="copy" size={14} color="#6e7a80" />
            </View>
          </View>
          <View style={styles.referenceRow}>
            <Text style={styles.referenceLabel}>Date & Time</Text>
            <Text style={styles.referenceValue}>{dateTime}</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.referenceRow}>
            <Text style={[styles.referenceValue, { fontSize: 18 }]}>Amount Paid</Text>
            <Text style={[styles.referenceValue, { color: '#019495', fontSize: 18 }]}>Rp {amountPaid.toLocaleString('id-ID')}</Text>
          </View>
        </View>

        <View style={styles.illustrationContainer}>
          <Image source={carPlugInPng as unknown as ImageSourcePropType} style={styles.illustrationImage} />
        </View>

        <Text style={styles.illustrationTitle}>Ready to Plug In</Text>
        <Text style={styles.illustrationText}>
          You can now safely connect the charger connector to your electric vehicle. Please ensure the cable is locked firmly into position.
        </Text>

        <View style={styles.statusPill}>
          <View style={styles.statusIndicator} />
          <Text style={styles.statusPillText}>
            {isPluggedIn ? 'Status: Plugged In' : 'Status: Awaiting Physical Connection...'}
          </Text>
        </View>

        <View style={styles.footerSpacer} />
        
        <View style={styles.footerAction}>
          <Pressable
            accessibilityState={{ disabled: !isPluggedIn }}
            disabled={!isPluggedIn}
            style={[styles.primaryButton, !isPluggedIn && styles.disabledPrimaryButton]}
            onPress={() =>
              sessionIdValue
                ? router.replace({ pathname: '/charging-flow/status', params: { sessionId: sessionIdValue } })
                : router.replace('/charging-flow/status')
            }
          >
            <View style={styles.buttonIconRow}>
              <ChargingFlowIcon name="connector" size={20} color="#004a4f" />
              <Text style={styles.primaryButtonText}>Start Charging Session</Text>
            </View>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}
