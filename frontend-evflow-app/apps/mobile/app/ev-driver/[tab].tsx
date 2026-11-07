import { EVDriverContainer } from '@evflow/features';
import { useLocalSearchParams } from 'expo-router';

// Static wallet-topup routes (wallet/topup.tsx, wallet/topup/success.tsx) win
// over this dynamic segment, so `walletFlow` is always null here.
export default function EvDriverTabRoute() {
  const { tab } = useLocalSearchParams<{ tab?: string }>();
  return <EVDriverContainer tab={typeof tab === 'string' ? tab : 'map'} walletFlow={null} />;
}