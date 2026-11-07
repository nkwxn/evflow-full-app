import { LoginScreen } from '@evflow/features';
import { useRouter } from 'expo-router';

export default function LoginRoute() {
  const router = useRouter();

  return (
    <LoginScreen
      onLogin={() => router.replace('/ev-driver')}
      onRegister={() => router.push('/register')}
    />
  );
}