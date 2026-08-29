import type { ManualVehicleInput, RoutePlanResponse, RoutePreferencesInput } from '@evflow/shared';
import type { LocationState } from './planRouteTypes';

export type ActiveNavigationSessionState = {
  status: 'active_navigation';
  result: RoutePlanResponse;
  destination: LocationState;
  navigationStartSocPct: number;
  estimatedCurrentSocPct: number;
  cumulativeDistanceKm: number;
  routeBaseDistanceKm: number;
  manualVehicle?: ManualVehicleInput;
  evModelId?: string;
  minimumArrivalSocPct: number;
  preferences: Required<RoutePreferencesInput>;
};

export type ActiveNavigationSessionAction =
  | { type: 'start'; session: ActiveNavigationSessionState }
  | { type: 'progress'; snapshot: Pick<ActiveNavigationSessionState, 'result' | 'estimatedCurrentSocPct' | 'cumulativeDistanceKm' | 'routeBaseDistanceKm'> }
  | { type: 'replace_route'; result: RoutePlanResponse }
  | { type: 'clear' };

export function activeNavigationSessionReducer(
  state: ActiveNavigationSessionState | null,
  action: ActiveNavigationSessionAction,
): ActiveNavigationSessionState | null {
  if (action.type === 'start') return action.session;
  if (action.type === 'clear') return null;
  if (!state) return null;
  if (action.type === 'replace_route') return { ...state, result: action.result };
  return { ...state, ...action.snapshot };
}

export type RemovableSubscription = { remove(): void };
export type WatchFactory<T> = (
  onValue: (value: T) => void,
  onError?: () => void,
) => Promise<RemovableSubscription | null>;

/** Owns exactly one watcher for one mounted active-navigation session. */
export class NavigationWatcherSession<T> {
  private subscription: RemovableSubscription | null = null;
  private pending: Promise<void> | null = null;
  private stopped = false;

  constructor(private readonly factory: WatchFactory<T>) {}

  start(onValue: (value: T) => void, onError?: () => void): Promise<void> {
    if (this.subscription || this.pending) return this.pending ?? Promise.resolve();
    this.stopped = false;
    this.pending = this.factory(onValue, onError).then((subscription) => {
      if (!subscription) onError?.();
      if (this.stopped) subscription?.remove();
      else this.subscription = subscription;
    }).finally(() => { this.pending = null; });
    return this.pending;
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.subscription?.remove();
    this.subscription = null;
  }
}

export function createRouteSessionCleaner(deleteSession: (id: string) => Promise<void>) {
  const deleted = new Set<string>();
  return async (id?: string | null) => {
    if (!id || deleted.has(id)) return;
    deleted.add(id);
    await deleteSession(id);
  };
}

export function shouldDeleteReplacedPlanningSession(
  previousRoutePlanId: string | undefined,
  nextRoutePlanId: string,
  waypointStationId?: string,
): boolean {
  return Boolean(previousRoutePlanId && previousRoutePlanId !== nextRoutePlanId && !waypointStationId);
}
