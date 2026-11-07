import { ResetPasswordScreen } from '@evflow/features';
import { useLocalSearchParams, useRouter } from 'expo-router';

export default function ResetPasswordRoute() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string | string[] }>();
  const tokenValue = Array.isArray(token) ? token[0] ?? null : token ?? null;

  return <ResetPasswordScreen token={tokenValue} onBackToLogin={() => router.replace('/login')} />;
}