import { ProfileSelectionScreen } from '@evflow/features';
import { useRouter } from 'expo-router';

export default function ProfileSelectionRoute() {
  const router = useRouter();

  return <ProfileSelectionScreen onBack={() => router.replace('/')} onContinue={() => router.push('/register')} />;
}