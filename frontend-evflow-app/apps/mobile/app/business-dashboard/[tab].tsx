import { BusinessPlannerContainer } from '@evflow/features';
import { useLocalSearchParams } from 'expo-router';

export default function BusinessDashboardTabRoute() {
  const { tab } = useLocalSearchParams<{ tab?: string }>();
  return <BusinessPlannerContainer tab={typeof tab === 'string' ? tab : undefined} />;
}