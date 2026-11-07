import { useMemo, useReducer, useState } from 'react';
import { Text, useWindowDimensions, View, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { BottomNavigation, evDriverContainerStyles as styles, SideMenu, type NavigationItem } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { DriverAssetIcon } from './components/DriverAssetIcon';
import { DriverMapScreen } from './DriverMapScreen';
import { MockDriverScreen } from './MockDriverScreen';
import { PlanRouteScreen } from './plan_route/PlanRouteScreen';
import { showDesktopNavigation, showMobileNavigation } from './plan_route/routeViewState';
import { ProfileScreen } from './ProfileScreen';
import { TopUpSuccessScreen, TopUpWalletScreen } from './TopUpWalletScreen';
import { WalletScreen } from './WalletScreen';
import type { DriverTabKey } from './types';
import { deleteRoutePlan } from '@evflow/shared';
import { activeNavigationSessionReducer } from './plan_route/navigationSession';

type EVDriverContainerProps = {
  /** Dynamic [tab] route param; static wallet-topup routes never reach here. */
  tab?: string;
  /** Always null today: wallet topup has its own static route files. */
  walletFlow?: 'topup' | 'success' | null;
};

export function EVDriverContainer({ tab, walletFlow = null }: EVDriverContainerProps = {}) {
  const [immersiveNavigation, setImmersiveNavigation] = useState(false);
  // Lost on refresh/native restart: matches today's behavior. There is no
  // GET /route-plans/{id} to rehydrate from. Deferred to Phase 5 backlog
  // (AsyncStorage keyed by route_plan_id).
  const [activeNavigationSession, dispatchNavigationSession] = useReducer(activeNavigationSessionReducer, null);
  const router = useRouter();
  const { height, width } = useWindowDimensions();
  const insets = useAppSafeAreaInsets();
  const desktop = width >= 768;
  const bottomNavOffset = desktop || immersiveNavigation ? 0 : 84 + insets.bottom;
  const topInset = insets.top;
  const items = useDriverNavigationItems();
  const activeTab = getActiveDriverTab(tab);
  const navigate = router.push;

  return (
    <View style={[styles.shell, styles.viewportShell, { height, maxHeight: height, minHeight: height }]}>
      {showDesktopNavigation(desktop, immersiveNavigation) ? (
        <View style={[styles.sidebarWrap, { paddingTop: topInset }]}>
          <SideMenu
            activeKey={activeTab}
            bottomContent={<Text style={styles.sidebarNote}>EV Driver Mode</Text>}
            items={items}
            onItemPress={(key) => {
              if (key === 'scan') {
                router.push('/charging-flow/scan');
              } else {
                router.push(getDriverTabPath(key as DriverTabKey));
              }
            }}
            subtitle="Driver"
            title="EV-FLOW"
          />
        </View>
      ) : null}

      <View
        style={[
          styles.content,
          styles.viewportContent,
          activeTab === 'map' && Platform.OS === 'web' && { touchAction: 'none' } as any
        ]}
      >
        {walletFlow === 'topup' ? (
          <TopUpWalletScreen bottomOffset={bottomNavOffset} topInset={topInset} />
        ) : walletFlow === 'success' ? (
          <TopUpSuccessScreen bottomOffset={insets.bottom} topInset={topInset} />
        ) : activeTab === 'map' ? (
          <DriverMapScreen
            bottomOffset={bottomNavOffset}
            onChargeHere={() => router.push('/charging-flow/scan')}
            topInset={topInset}
          />
        ) : activeTab === 'wallet' ? (
          <WalletScreen bottomInset={insets.bottom} bottomOffset={bottomNavOffset} topInset={topInset} />
        ) : activeTab === 'profile' ? (
          <ProfileScreen
            bottomOffset={bottomNavOffset}
            topInset={topInset}
            onLogout={async () => {
              if (activeNavigationSession?.result.route_plan_id) {
                try { await deleteRoutePlan(activeNavigationSession.result.route_plan_id); } catch { /* Server expiry remains the fallback. */ }
              }
              dispatchNavigationSession({ type: 'clear' });
            }}
          />
        ) : activeTab === 'plan_route' ? (
          <PlanRouteScreen
            activeNavigationSession={activeNavigationSession}
            bottomOffset={bottomNavOffset}
            dispatchNavigationSession={dispatchNavigationSession}
            onNavigationModeChange={setImmersiveNavigation}
            topInset={topInset}
          />
        ) : (
          <MockDriverScreen tabKey={activeTab} topInset={topInset} />
        )}


        {showMobileNavigation(desktop, immersiveNavigation, walletFlow === 'success') ? (
          <View style={[styles.bottomNavWrap, { paddingBottom: insets.bottom }]}>
            <BottomNavigation
              activeKey={activeTab}
              items={items}
              onItemPress={(key) => {
                if (key === 'scan') {
                  router.push('/charging-flow/scan');
                } else {
                  router.push(getDriverTabPath(key as DriverTabKey));
                }
              }}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

function getActiveDriverTab(tab: string | undefined): DriverTabKey {
  if (tab === 'map' || tab === 'wallet' || tab === 'scan' || tab === 'plan_route' || tab === 'profile') {
    return tab;
  }

  return 'map';
}

function getDriverTabPath(tab: DriverTabKey) {
  return `/ev-driver/${tab}`;
}

function useDriverNavigationItems(): NavigationItem[] {
  return useMemo(
    () => [
      {
        key: 'map',
        label: 'Map',
        icon: ({ color }) => <DriverAssetIcon color={color} name="map" />
      },
      {
        key: 'wallet',
        label: 'Wallet',
        icon: ({ color }) => <DriverAssetIcon color={color} name="wallet" />
      },
      {
        key: 'scan',
        label: 'Scan',
        prominent: true,
        icon: ({ color }) => <DriverAssetIcon color={color} name="scan" />
      },
      {
        key: 'plan_route',
        label: 'Plan Route',
        icon: ({ color }) => <DriverAssetIcon color={color} name="plan_route" />
      },
      {
        key: 'profile',
        label: 'Profile',
        icon: ({ color }) => <DriverAssetIcon color={color} name="profile" />
      }
    ],
    []
  );
}
