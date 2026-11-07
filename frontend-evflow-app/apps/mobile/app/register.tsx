import { RegistrationScreen } from '@evflow/features';
import { useRouter } from 'expo-router';

export default function RegistrationRoute() {
  const router = useRouter();

  return (
    <RegistrationScreen
      onBack={() => router.replace('/login')}
      onLogin={() => router.replace('/login')}
      onRegister={() => router.replace('/ev-driver')}
    />
  );
}