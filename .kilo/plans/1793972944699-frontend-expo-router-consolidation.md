# Plan: Consolidate frontend-evflow-app onto apps/mobile (Expo Router, Native + Web)

## Context

**Goal:** Run the entire EVFlow frontend from `apps/mobile` only, producing both native (Android/iOS) and web builds through a single Expo Router + Metro pipeline. Delete `apps/web` (Vite) and the dead `packages/maps` after parity is verified.

**Current state (verified against graphify-out/GRAPH_REPORT.md 2026-11-06, commit `64479b38`, plus direct source inspection):**

- npm-workspace monorepo: `apps/mobile` (Expo SDK 54.0.35 shell), `apps/web` (Vite 8 shell), `packages/{shared,ui,features,maps}` exposed as TS source (no intermediate builds).
- Both app shells are thin: `apps/mobile/App.tsx` (68 LOC) and `apps/web/src/main.tsx` (26 LOC) each wrap the same `AppRouter` from `@evflow/features`.
- Routing: react-router with platform variants (`AppRouter.tsx` = BrowserRouter via `react-router-dom`; `AppRouter.native.tsx` = NativeRouter via `react-router-native`; all other 16 screen files import from `react-router` core). Routes centralized in `packages/features/src/routing/AppRoutes.tsx`.
- Platform variants exist for: router, camera (`html5-qrcode` web / `expo-camera` native), location (browser geolocation / `expo-location`), receipts (`html2pdf.js` web / `expo-print` native), safe-area insets, icons, sliders, font install.
- Maps: real implementations are `packages/ui/src/components/LeafletMap.web.tsx` (785 LOC, dynamic `import('leaflet')`) and `LeafletMap.tsx` (628 LOC, Leaflet HTML in `react-native-webview`). `packages/maps` is a dead placeholder (both `MapView` variants render text; unused by product screens).
- `apps/web/src/styles.css` contains ONLY Space Grotesk `@font-face` rules (pointing into `node_modules` TTFs) + html/body sizing/font-family. No other global CSS. The font-install hooks in both shells already handle fonts; the CSS does not survive Metro export and is not needed — `useFonts` covers web too.
- `apps/web/dist/` is NOT tracked in git (already ignored via `apps/*/dist/` in `.gitignore`) — it is only a local artifact. No repo cleanup needed for it.

**In-memory flow states that must migrate to URL params (all verified in source):**

| State | Where | Today's behavior | Backend recovery |
|---|---|---|---|
| Onboarding `evModelId` | `location.state` from `VehicleSelectScreen.tsx:132` → `ConnectorSelectScreen.tsx:45` | Dies on refresh | id only — no fetch needed; port validator in `vehicleSelection.ts` |
| Charging selection (`station`, `connector`) | `ScanSpkluScreen` → `location.state` → `InitializeChargingScreen.tsx:58` | Dies on refresh | `fetchStation(id)` EXISTS (`shared/src/stations/api.ts:249`) |
| Charging session (`session`, `actualPowerKw`, `energy`, `estimatedMinutes`) | `InitializeChargingScreen.tsx:175-176` → success/status/successful | Dies on refresh | `fetchChargingSession(sessionId)` EXISTS (`shared/src/charging/api.ts:103`); `settleChargingSession` idempotent, so re-mounts never double-credit. `TransactionSuccessScreen` consumes only `session.{id, deposit_idr, created_at}` — all in the fetch response. `ChargingStatusScreen` derives `stationName`/`connectorType`/`base_rate_idr` from the session response (`ChargingSessionApiResponse` has `station_name`, `connector_type`, `base_rate_idr`, `power_kw`, `energy_kwh`) |
| Wallet topup (`topupId`, `amountIdr`, `invoiceUrl`) | `TopUpWalletScreen.tsx:152-156` | **Partially URL-based already**: `parseTopupIdFromSearch` (`TopUpWalletScreen.tsx:257`) handles Xendit's `?topup_id=` redirect | `fetchWalletTopup(topupId)` EXISTS (`shared/src/wallet/api.ts:65`); poll loop already present in `TopUpSuccessScreen` |
| `activeNavigationSession` (full `RoutePlanResponse` + SOC tracking) | `useReducer` in `EVDriverContainer.tsx:21`, passed to `PlanRouteScreen.tsx:41` | Dies on refresh/native restart | **NOT recoverable**: backend has only POST /route-plans, POST /route-plans/active/evaluate, DELETE — no GET by id |
| `selectedRole` in `AppRoutes.tsx:16` | radio-highlight state for ProfileSelectionScreen | Dies on refresh | Never consumed downstream (verified: `RegistrationScreen` has no role logic) — becomes plain local state in the screen |

**Env-read facts (verified):** exactly 3 files read `VITE_*` via `import.meta.env` casts: `shared/src/api/baseUrl.web.ts` (Vite variant of `baseUrl.ts`), `features/src/login/demoCredentials.web.ts`, and the call-site `DemandHeatmapScreen.tsx:223` which passes `import.meta.env` into the pure `tomtomKey(env)` (`business/traffic/tomtomTraffic.ts`). Native counterparts (`baseUrl.ts`, `demoCredentials.ts`) already read `process.env.EXPO_PUBLIC_*`. Expo/Metro inlines `EXPO_PUBLIC_*` into web builds too, so all `.web.ts` env variants can merge into their `process.env` counterparts and `import.meta.env` disappears entirely. `tomtomKey`'s key name renames to `EXPO_PUBLIC_TOMTOM_API_KEY` inside the function and its test (`tomtomTraffic.test.ts` injects `{VITE_TOMTOM_API_KEY}`). `tomtomKey`'s signature (takes env object) stays — test injection pattern unaffected. `.env.example` lists `VITE_*` values to rename (docs task).

**Auth-session fact (verified):** `getAuthHeaders()` is synchronous and consumed at request time by 6+ API modules (`wallet/api.ts`, `routes/routeApi.ts`, `charging/api.ts`, `planner/api.ts`, `stations` status fetch, `support`). Native persistence via async-only SecureStore would require an app-start hydration gate — deferred (decision 5).

**Dependency facts (verified):** `expo-router`, `expo-constants`, `expo-linking`, `react-native-screens` are NOT installed. `react-dom`, `react-native-web`, `react-native-safe-area-context`, `expo-status-bar` ARE installed. `react-router`/`react-router-dom`/`react-router-native` at root + `apps/mobile` + `packages/features` peerDeps.

**Decisions (confirmed by user):**
1. Migrate to **expo-router** (file-based routes under `apps/mobile/app/`), not react-router.
2. **Parallel cutover**: build expo-router + web export inside `apps/mobile` while `apps/web` stays runnable; delete `apps/web` and `packages/maps` only after the parity checklist passes.
3. **All flow state in URL params** — ids in params, objects re-fetched via existing API clients; never serialize objects into URLs.
4. **activeNavigationSession: accept loss on refresh/kill** (matches today's behavior), defer recovery to follow-up.
5. **Native auth-session persistence deferred to Phase 5** (SecureStore needs an async hydration gate that `getAuthHeaders()`'s sync contract can't absorb without an app-start redesign).

**Architecture rating: 7/10** — excellent layering and platform-suffix discipline; docked for dual-bundler duplication, god components (`DriverMapScreen.tsx` 1,491 LOC, `DemandHeatmapScreen.tsx` 1,518 LOC), fragile in-memory flow state, dead `packages/maps`.

## Constraints

- npm is the package-manager convention (lockfile, Containerfile use it) despite stale `packageManager: yarn` metadata in root package.json.
- `apps/mobile/app.json` already declares `"web": { "bundler": "metro" }` and `scheme: evflow`.
- Metro already watches the whole workspace (`metro.config.js` watchFolders) and resolves `.native.tsx`/`.web.tsx` suffixes by default.
- Backend API is **unchanged** (frontend-only migration); this plan touches `frontend-evflow-app/`, its `Containerfile`, and `deploy/nginx.conf.template` only.
- External param-name contracts: `token` (password-reset email link) and `topup_id` (Xendit hosted-page redirect) must NOT be renamed. New params (`stationId`, `connectorType`, `sessionId`, `kwh`, `evModelId`) follow camelCase.
- Source-text-asserting vitest tests will need literal updates: `savedSitesLifecycle.test.ts:36` asserts `navigate('/business-dashboard/demand-heatmap')` in `SavedSitesScreen.tsx`; `tomtomTraffic.test.ts` asserts `VITE_TOMTOM_API_KEY` key name; grep both lifecycle test files for other navigation/env literals when touched.
- The `installDefaultFont` monkey-patch on `Text.render` (`App.tsx:33-50`) is load-bearing for native font-family mapping — moves to `_layout.tsx` unchanged.

## Target architecture (after cutover)

```
apps/mobile/                     (the only app)
  app/                           expo-router file routes (see Route Map)
  app/_layout.tsx                root layout: SafeAreaProvider, useFonts, StatusBar, ReceiptPdfViewer
  app.json                       + "plugins": ["expo-router"], web.output: "single"
  eas.json                       (new) EAS build profiles: android, ios
  (index.js and App.tsx deleted — replaced by expo-router/entry)
packages/shared, ui, features    unchanged boundaries; react-router imports removed
packages/maps                    DELETED
apps/web                         DELETED after parity
```

- One bundler (Metro), one dev server (`expo start`, `expo start --web` for browser), one env system (`EXPO_PUBLIC_*` on `process.env`), one router (expo-router), one build (`eas build` native / `npx expo export -p web`).
- Web output: `"web": { "bundler": "metro", "output": "single" }` produces a single `index.html` SPA, so `deploy/nginx.conf.template`'s existing `try_files $uri /index.html` fallback and `location /assets/` immutable caching keep working unchanged.

## Route Map (react-router → expo-router)

Create `apps/mobile/app/` (expo-router auto-registers file routes):

| Route file | Old route | Screen component | Params (URL contract) |
|---|---|---|---|
| `app/index.tsx` | `/` | QuickLoginScreen | — |
| `app/login.tsx` | `/login` | LoginScreen | — |
| `app/register.tsx` | `/register` | RegistrationScreen | — |
| `app/reset-password.tsx` | `/reset-password` | ResetPasswordScreen | `?token=` (email-link contract) |
| `app/profile-selection.tsx` | `/profile-selection` | ProfileSelectionScreen | — (`selectedRole` becomes internal state) |
| `app/onboarding/vehicle.tsx` | `/onboarding/vehicle` | VehicleSelectScreen | — |
| `app/onboarding/connector.tsx` | `/onboarding/connector` | ConnectorSelectScreen | `?evModelId=` |
| `app/ev-driver/index.tsx` | redirect `/ev-driver` → `/ev-driver/map` | `<Redirect href="/ev-driver/map" />` | — |
| `app/ev-driver/[tab].tsx` | `/ev-driver/:tab` | EVDriverContainer | path param `tab` (map/wallet/scan/plan_route/profile) |
| `app/ev-driver/wallet/topup.tsx` | `/ev-driver/wallet/topup` | TopUpWalletScreen | — |
| `app/ev-driver/wallet/topup/success.tsx` | `/ev-driver/wallet/topup/success` | TopUpSuccessScreen | `?topup_id=` (Xendit contract) |
| `app/charging-flow/scan.tsx` | `/charging-flow/scan` | ScanSpkluScreen (.native/.web variants kept) | — |
| `app/charging-flow/initialize.tsx` | `/charging-flow/initialize` | InitializeChargingScreen | `?stationId=&connectorType=` |
| `app/charging-flow/success.tsx` | `/charging-flow/success` | TransactionSuccessScreen | `?sessionId=` |
| `app/charging-flow/status.tsx` | `/charging-flow/status` | ChargingStatusScreen | `?sessionId=` |
| `app/charging-flow/successful.tsx` | `/charging-flow/successful` | ChargingSuccessfulScreen | `?sessionId=&kwh=` |
| `app/business-dashboard/index.tsx` | redirect → `/business-dashboard/demand-heatmap` | — | — |
| `app/business-dashboard/[tab].tsx` | `/business-dashboard/:tab` | BusinessPlannerContainer | path param `tab` |
| `app/_layout.tsx` | (root) | SafeAreaProvider, useFonts, StatusBar, ReceiptPdfViewer (native) | — |
| `app/+not-found.tsx` | `*` → `/` | redirect | — |

Route files stay thin (each wraps the existing screen component from `@evflow/features`), preserving the "apps are shells, screens live in features" rule from `docs/ARCHITECTURE.md`.

**Route conflict note:** expo-router gives static segments priority over dynamic ones, so `app/ev-driver/wallet/topup.tsx` wins over `app/ev-driver/[tab].tsx` — mirrors react-router's behavior today. No restructuring needed.

**EVDriverContainer internals:** `getActiveDriverTab`/`getWalletFlow` (currently parsing `useLocation().pathname`) switch to `usePathname()`/`useLocalSearchParams()` — the tab key comes from the `[tab]` route param directly. `activeNavigationSession` useReducer stays in the container (decision 4).

## Tasks (ordered)

### Phase 0 — Baseline
1. Record baseline: `npm run typecheck`, `npm test`, `npm run build:web` all green; note current web bundle size (~1.99 MB min / 582 KB gzip per docs/PROJECT_STATUS.md) as the parity yardstick.

### Phase 1 — Expo Router scaffold inside apps/mobile
2. Install in `apps/mobile`: `npm install expo-router react-native-screens expo-constants expo-linking` (`expo-status-bar`/`react-native-safe-area-context` already installed). Set `"main": "expo-router/entry"` in `apps/mobile/package.json`; delete `apps/mobile/index.js`; move `App.tsx`'s font-install logic into `_layout.tsx` and delete `App.tsx`.
3. `app.json`: add `"plugins": ["expo-router"]`; change web block to `"web": { "bundler": "metro", "output": "single" }` (scheme `evflow` already set).
4. Create `app/_layout.tsx`: SafeAreaProvider, `useFonts` Space Grotesk loading (with the `installDefaultFont` monkey-patch moved from App.tsx), StatusBar, and native-only `<ReceiptPdfViewer />` mount (web downloads receipts via html2pdf blob — matches today's `Platform.OS !== 'web'` gating in `WalletScreen.tsx:363`).
5. Create all route files per the Route Map. Keep `packages/features/src/routing/*` on disk until Phase 4 (apps/web still imports `AppRouter`/`AppRoutes`).

### Phase 2 — Migrate navigation in packages/features
6. Replace `react-router` imports with expo-router (`useRouter`, `useLocalSearchParams`, `usePathname`, `router.push/replace/back`, `<Redirect>`) across the 16 screen files that import `react-router` (verified list: `charging_flow/{ScanSpkluScreen,ScanSpkluScreen.native,InitializeChargingScreen,TransactionSuccessScreen,ChargingStatusScreen,ChargingSuccessfulScreen}`, `onboarding/{VehicleSelectScreen,ConnectorSelectScreen}`, `login/QuickLoginScreen`, `ev_driver/{EVDriverContainer,WalletScreen,ProfileScreen,TopUpWalletScreen}`, `business/{BusinessPlannerContainer,BusinessDashboardScreen,SavedSitesScreen}`).
   - `navigate('/x')` → `router.push('/x')`; `navigate('/x', { replace: true })` → `router.replace('/x')`; `navigate(-1)` → `router.back()`
   - `useLocation().pathname` parsing → `usePathname()` / `useLocalSearchParams()`
   - `AppRoutes.tsx` route-wrapper components (`LoginRoute`, `ProfileSelectionRoute`, `ResetPasswordRoute`, `RegistrationRoute`) collapse into their thin route files; the redirect `<Route>`s become `<Redirect>` route files.
7. **URL-param flow state migration** (one flow at a time, manually tested before the next: onboarding → topup → charging):
   - **Onboarding:** `VehicleSelectScreen` → `router.push({ pathname: '/onboarding/connector', params: { evModelId } })`; `ConnectorSelectScreen` reads `useLocalSearchParams().evModelId`, ports the `vehicleSelection.ts` validator to parse the param string.
   - **Charging scan→initialize:** `ScanSpkluScreen` passes `stationId` + `connectorType` from the validated `ValidSpkluSelection`; `InitializeChargingScreen` replaces its `location.state` branch (lines 55-64) with `fetchStation(stationId)` + connector lookup by type in `station.connectors`; keep the existing no-params fallback branch (nearest-station discovery, lines 66-98) so a params-less deep link still works.
   - **Charging downstream:** `InitializeChargingScreen` navigates to `/charging-flow/success?sessionId=X`; `TransactionSuccessScreen` re-fetches `fetchChargingSession(sessionId)` for `{id, deposit_idr, created_at}`; `ChargingStatusScreen` navigates `?sessionId=X` and re-fetches the session, deriving `stationName`/`connectorType`/`base_rate_idr`/`power_kw`/purchased `energy_kwh` from the response (simulation timers restart — acceptable, matches "charging progress is simulated" in docs/PROJECT_STATUS.md); `ChargingStatusScreen`→`successful` passes `?sessionId=X&kwh=Y` (delivered amount — needs a param because it's simulation output with no backend source until settlement); `ChargingSuccessfulScreen` keeps `settleChargingSession(sessionId, kwh)` — idempotent, safe on re-mount.
   - **Wallet topup:** preserve `?topup_id=` exactly; `TopUpSuccessScreen` drops the `location.state` branch, keeps `parseTopupIdFromSearch`-equivalent param read + existing `fetchWalletTopup` poll loop.
   - **Profile selection:** delete the `selectedRole` lift; `ProfileSelectionScreen` holds its own radio state.
8. **activeNavigationSession (decision 4):** `useReducer` in `EVDriverContainer` unchanged; props pass-through untouched. Web refresh/native restart returns user to the plan-route form — identical to today. Add a code comment noting the deferral + Phase 5 backlog entry.
9. Remove `react-router`, `react-router-dom`, `react-router-native` from `packages/features/package.json` peerDeps (and root/`apps/mobile` deps at Phase 4 — apps/web needs them until then). Delete `routing/` only at Phase 4 cutover.
10. Update source-text-asserting tests: `savedSitesLifecycle.test.ts:36` (navigate literal → expo-router call), `tomtomTraffic.test.ts` key-name literals (`VITE_TOMTOM_API_KEY` → `EXPO_PUBLIC_TOMTOM_API_KEY`). Grep lifecycle tests for other navigation/env literals.

### Phase 3 — Web export through Metro
11. Add `react-dom` to `apps/mobile` deps; `react-native-web` already hoisted at root (verify hoisting after install; add to mobile if not).
12. Global CSS: do NOT port `apps/web/src/styles.css` — its `@font-face` rules point into `node_modules` (would break under Metro) and `useFonts` covers web; html/body sizing defaults suffice. CSS dies with apps/web at Phase 4.
13. Env consolidation: merge `.web.ts` env variants into their `process.env` counterparts — `baseUrl.web.ts` folds into `baseUrl.ts` (native version already reads `EXPO_PUBLIC_EVFLOW_API_BASE_URL` with the same precedence chain + dev-host logic; keep `assertSecureProductionApiBaseUrl`), `demoCredentials.web.ts` folds into `demoCredentials.ts` (both read `EXPO_PUBLIC_DEMO_PASSWORD` after merge), `DemandHeatmapScreen.tsx:223` call-site changes `import.meta.env` → `process.env`, `tomtomKey` reads `EXPO_PUBLIC_TOMTOM_API_KEY`. Delete the `.web.ts` env files. (Metro inlines `EXPO_PUBLIC_*` for web; `import.meta.env` disappears entirely.)
14. Add `leaflet` to `apps/mobile` deps (currently only in `apps/web`/root) and verify the dynamic `import('leaflet')` in `LeafletMap.web.tsx` resolves under Metro; confirm `tomtomTraffic.ts` overlay renders in the Metro web build.
15. Web build check: `npx expo export --platform web --output-dir dist` — with `web.output: "single"` produces single-page `dist/index.html` + hashed `/assets/`; `deploy/nginx.conf.template` needs NO changes.
16. Update `Containerfile`: replace `npm run build:web` with `npx expo export --platform web --output-dir dist` (run in mobile workspace context); rename build args `VITE_EVFLOW_API_BASE_URL`→`EXPO_PUBLIC_EVFLOW_API_BASE_URL`, `VITE_DEMO_PASSWORD`→`EXPO_PUBLIC_DEMO_PASSWORD`, `VITE_TOMTOM_API_KEY`→`EXPO_PUBLIC_TOMTOM_API_KEY`; nginx runtime stage unchanged.
17. Add `apps/mobile/eas.json`: `production`/`preview` profiles for android + ios (web served by nginx; no EAS web hosting).

### Phase 4 — Parity verification, then cutover
18. **Parity checklist (all green before any deletion):**
    - `npm run typecheck` + `npm test` green (lifecycle-test literals updated).
    - `npx expo export -p web` succeeds; served via updated Containerfile (podman): every route loads — login → driver map (Leaflet renders, markers fetch), charging scan (html5-qrcode camera), plan route, business dashboard tabs (heatmap + saved sites + traffic overlay when key present), wallet topup (Xendit invoice → success polling), receipt download (html2pdf blob).
    - **Refresh/deep-link matrix:** `/onboarding/connector?evModelId=X` reload; `/charging-flow/initialize?stationId=X&connectorType=Y` direct entry AND params-less fallback; `/charging-flow/status?sessionId=X` reload mid-simulation (re-fetch + simulation restart OK); `/charging-flow/successful?sessionId=X&kwh=Y` reload → settle retry (idempotent); `/ev-driver/wallet/topup/success?topup_id=X` via Xendit redirect AND manual reload; `/reset-password?token=X` from email link; `evflow://charging-flow/scan` on device.
    - Native smoke: Expo Go Android/iOS — login → map → scan (expo-camera) → initialize → status → successful; receipt PDF opens in WebView viewer; topup flow.
    - Bundle size ≤ ~2.5 MB min (1.99 MB baseline + 25%).
    - Known accepted loss: active-navigation refresh (decision 4) — verify no crash, clean form return.
19. On green: delete `apps/web/`, `packages/maps/`, `packages/features/src/routing/`; prune root deps no longer used (`vite`, `@vitejs/plugin-react`, `html2pdf.js` — keep `leaflet`, moved to mobile); drop `@evflow/maps` from `tsconfig.base.json` paths, `vitest.config.ts` coverage excludes, package.json workspaces refs; update root scripts (`web` → `expo start --web`, `build:web` → `expo export -p web`, run in mobile workspace); remove `react-router*` from all manifests; final `npm install`; verify `npm ci` works in Containerfile.
20. Docs: update `frontend-evflow-app/README.md` (structure, run/build commands), `docs/ARCHITECTURE.md` (Frontend Structure + Client Routing sections), `docs/CONFIGURATION.md` (VITE_* → EXPO_PUBLIC_*), `docs/PROJECT_STATUS.md` (capability matrix: Web deployment → Expo export; Mobile deployment → eas.json tracked), `frontend-evflow-app/.env.example` (VITE_* lines → EXPO_PUBLIC_* with same values).

### Phase 5 — Follow-ups (explicitly out of scope for this migration)
- Native auth-session persistence: expo-secure-store with app-start hydration gate in `_layout.tsx` (block render until hydrated), OR refactor `getAuthHeaders()` consumers to an async token-provider API — needs its own design pass because 6+ sync call-sites exist.
- activeNavigationSession rehydration (AsyncStorage keyed by `route_plan_id`).
- God-component decomposition (`DriverMapScreen`, `DemandHeatmapScreen`).
- Route guards (auth/role) at expo-router layout level; global 401 interceptor.
- Native map replacement (react-native-maps/Mapbox) instead of Leaflet-in-WebView with unpkg CDN assets.
- OpenAPI-generated API clients to stop handwritten-contract drift.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Metro web bundle larger than Vite (~2 MB baseline) | Measure at task 15; accept ≤25%; `EXPO_PUBLIC_*` unset → TomTom layer silently inert. |
| Dynamic `import('leaflet')` fails under Metro | Task 14 verifies explicitly; fallback: static import in `LeafletMap.web.tsx`. |
| Exposing `sessionId`/`stationId` in URLs | Sessions are bearer-auth'd server-side (`fetchChargingSession` requires auth); settlement idempotent; station ids are public catalogue data. No new exposure. |
| `location.state` removal breaks flows mid-migration | Task 7 orders flows: onboarding (smallest) → topup (already URL-based) → charging (biggest); manual test each before next. |
| Xendit `topup_id` param contract break | Route Map pins the name; parity checklist includes the live Xendit redirect test. |
| Sync `getAuthHeaders()` vs deferred SecureStore | Decision 5 defers it; migration ships with today's session semantics (web sessionStorage, native module memory). |
| Lifecycle tests assert literal source strings | Task 10 updates them; `npm test` gates every phase. |
| Lockfile churn | One `npm install` per phase; `npm ci` re-verified in Containerfile at task 19. |
| Expo Go incompatibility with new native deps | All added deps (`expo-router`, `react-native-screens`, `expo-constants`, `expo-linking`) ship in Expo Go / SDK 54; no dev-client needed. |
| Lost `activeNavigationSession` on refresh | Matches today exactly (decision 4); documented in code + Phase 5 backlog. |

## Validation plan

1. After each phase: `npm run typecheck` + `npm test`.
2. After Phase 3: `npx expo export -p web`, serve via Containerfile, run the route checklist (task 18).
3. After Phase 4: clean checkout → `npm ci && npx expo export -p web` inside Containerfile to prove no stale-local-state dependence.
4. Native smoke on Expo Go (Android emulator + iOS simulator): full charging flow + topup + receipt viewer.
5. Refresh/deep-link matrix (task 18, third bullet) — the acceptance test for decision 3.

## Notes for the implementer

- **Param names are contracts**: `token`, `topup_id` externally fixed; `stationId`, `connectorType`, `sessionId`, `kwh`, `evModelId` camelCase.
- `kwh` on the `successful` route is simulation output (delivered energy) — it has no backend source until settlement, so it must travel in the URL.
- `InitializeChargingScreen`'s params-less fallback branch (nearest-station discovery, lines 66-98) already exists — the params-less deep-link path is nearly free.
- Two entry files (`index.js`, `App.tsx`) die in Phase 1; `registerRootComponent` → `expo-router/entry`.
- The `installDefaultFont` monkey-patch on `Text.render` moves to `_layout.tsx` unchanged — load-bearing for native font mapping.
- `demoCredentials.ts` (native variant) and `demoCredentials.web.ts` will be identical after env merge — delete the `.web` variant, keep the native name.
- `baseUrl.ts` (native) already contains the full dev-host LAN/emulator detection logic (`getDevServerHost`, `LOCAL_HOST_PATTERN`) — the merged single file keeps all of it; only the env-var name chain (`EXPO_PUBLIC_*` first) matters.