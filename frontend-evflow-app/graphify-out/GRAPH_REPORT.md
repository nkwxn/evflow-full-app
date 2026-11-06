# Graph Report - frontend-evflow-app  (2026-08-29)

## Corpus Check
- 259 files · ~135,538 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1809 nodes · 3789 edges · 130 communities (92 shown, 38 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 19 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `71737d01`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ui/src/index.ts
- peerDependencies
- HelpDeskScreen.tsx
- EVDriverContainer.tsx
- DemandHeatmapScreen.tsx
- planner/api.ts
- DriverMapScreen.tsx
- PlanRouteScreen.tsx
- areaFilterMode.ts
- siteFeasibilityLogic.ts
- ActiveNavigationScreen.tsx
- areaPrediction.ts
- AppRoutes.tsx
- routeApi.ts
- competitiveLandscape.ts
- WalletScreen.tsx
- TripSimulationScreen.tsx
- BusinessDashboardScreen.tsx
- plannerApiAdapters.ts
- routePlanningLogic.ts
- demandHeatmap.ts
- useSiteFeasibilityDetail.ts
- PeakHoursChart.tsx
- apiStationStatus.ts
- expo
- nearbyAlternatives.ts
- ConnectorSelectScreen.tsx
- TopUpWalletScreen.tsx
- compilerOptions
- aggregateConnectorStatuses.ts
- LeafletMap.web.tsx
- ui/package.json
- styles.ts
- areaFilterSession.ts
- location.web.test.ts
- features/src/index.ts
- SavedSitesScreen.tsx
- FinancialProjectionsTab.tsx
- stationDetailState.ts
- dependencies
- stations/api.ts
- shared/src/index.ts
- baseUrl.ts
- SvgAssetIcon.tsx
- QuickLoginScreen.tsx
- ProfileSelectionScreen.tsx
- radiusScope.ts
- NearbyStationsTab.tsx
- charging/api.ts
- dependencies
- RegistrationScreen.tsx
- ConnectorAvailabilityRow.tsx
- DestinationSearchModal.tsx
- maps/package.json
- dependencies
- SiteFeasibilitySheet.tsx
- mobile/package.json
- tsconfig.json
- scripts
- validation.ts
- MapView.web.tsx
- EVFlow Frontend
- mobile/tsconfig.json
- web/tsconfig.json
- devDependencies
- location.ts
- shared/src/types.ts
- web/package.json
- package.json
- overrides
- siteFeasibilityLifecycle.test.ts
- features/tsconfig.json
- maps/tsconfig.json
- ui/tsconfig.json
- scripts
- devDependencies
- connectorStatusPalette.ts
- shared/tsconfig.json
- generate_components.js
- spkluMarkerSvg.ts
- shared/package.json
- App.tsx
- metro.config.js
- generate_icons.js
- savedSitesLifecycle.test.ts
- driverMapIcons.native.ts
- BatteryLevelInput.tsx
- PlatformSlider.tsx
- features/src/vite-env.d.ts
- ChargingFlowIcon.native.tsx
- SvgAssetIcon.native.tsx
- @evflow/ui
- expo-camera
- expo-file-system
- expo-font
- @expo-google-fonts/space-grotesk
- expo-intent-launcher
- expo-location
- @expo/metro-config
- expo-print
- expo-sharing
- expo-status-bar
- react
- @react-native-picker/picker
- react-native-safe-area-context
- react-native-svg
- react-native-webview
- react-router
- @evflow/maps
- @evflow/shared
- @evflow/ui
- expo-intent-launcher
- expo-sharing
- html2pdf.js
- leaflet
- react-dom
- react-router-dom
- vite
- @vitejs/plugin-react
- expo
- expo-font
- react-native
- react-native-webview
- react-router-dom
- demoCredentials.web.ts
- profileSelectionIcons.native.ts

## God Nodes (most connected - your core abstractions)
1. `DriverMapScreen()` - 36 edges
2. `DemandHeatmapScreen()` - 34 edges
3. `useAppSafeAreaInsets()` - 33 edges
4. `ActiveNavigationScreen()` - 23 edges
5. `SvgAssetIcon()` - 21 edges
6. `getAuthHeaders()` - 21 edges
7. `plannerRequest()` - 17 edges
8. `useSiteFeasibilityDetail()` - 15 edges
9. `SavedSitesScreen()` - 13 edges
10. `getEvflowApiBaseUrl()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `applyScannerTorch()` --references--> `html5-qrcode`  [EXTRACTED]
  packages/features/src/charging_flow/ScanSpkluScreen.tsx → package.json
- `ScanSpkluScreen()` --references--> `html5-qrcode`  [EXTRACTED]
  packages/features/src/charging_flow/ScanSpkluScreen.tsx → package.json
- `DemandHeatmapScreen()` --indirect_call--> `plannerCandidateToOptimalSite()`  [INFERRED]
  packages/features/src/business/DemandHeatmapScreen.tsx → packages/features/src/business/plannerApiAdapters.ts
- `ModelPredictionLegend()` --calls--> `suitabilityKeyNote()`  [EXTRACTED]
  packages/features/src/business/DemandHeatmapScreen.tsx → packages/features/src/business/site-prediction/areaPrediction.ts
- `ScanSpkluScreen()` --indirect_call--> `validateSpkluPayload()`  [INFERRED]
  packages/features/src/charging_flow/ScanSpkluScreen.native.tsx → packages/features/src/charging_flow/spkluQrValidation.ts

## Import Cycles
- None detected.

## Communities (130 total, 38 thin omitted)

### Community 0 - "ui/src/index.ts"
Cohesion: 0.10
Nodes (31): html5-qrcode, html5-qrcode, ChargingStatusScreen(), ChargingSuccessfulScreen(), ChargingFlowHeader(), ChargingFlowHeaderProps, ChargingFlowIcon(), ChargingIconName (+23 more)

### Community 1 - "peerDependencies"
Cohesion: 0.04
Nodes (48): dependencies, @evflow/maps, @evflow/shared, @evflow/ui, expo-file-system, expo-intent-launcher, expo-print, expo-sharing (+40 more)

### Community 2 - "HelpDeskScreen.tsx"
Cohesion: 0.09
Nodes (39): HelpDeskScreen(), HelpDeskScreenProps, styles, SupportSentScreen(), SupportSentScreenProps, mockedGetAuthHeaders, TICKET, describeSupportFailure() (+31 more)

### Community 3 - "EVDriverContainer.tsx"
Cohesion: 0.08
Nodes (35): BusinessPlannerContainer(), BusinessPlannerIcon(), icons, BusinessPlannerTabKey, businessPlannerTabs, getBusinessPlannerNavigationItems(), getBusinessPlannerPath(), getBusinessPlannerTab() (+27 more)

### Community 4 - "DemandHeatmapScreen.tsx"
Cohesion: 0.08
Nodes (33): poiPoints(), commercialPoiIcon, currentLocationIcon, heatmapLayerIcon, landUseIcon, layersIcon, modelPredictionIcon, optimalSiteIcon (+25 more)

### Community 5 - "planner/api.ts"
Cohesion: 0.07
Nodes (37): getSiteFeasibility(), defaultPlannerWeights, fetchPlannerBenchmark(), fetchPlannerCandidates(), fetchPlannerCell(), fetchPlannerLandUse(), fetchPlannerModel(), fetchPlannerPois() (+29 more)

### Community 6 - "DriverMapScreen.tsx"
Cohesion: 0.08
Nodes (40): ConnectorInfo, ConnectorRow(), ConnectorRowProps, Coordinates, defaultMapView, DrawerMode, DriverMapScreen(), DriverMapScreenProps (+32 more)

### Community 7 - "PlanRouteScreen.tsx"
Cohesion: 0.09
Nodes (32): NavigationSnapshot, RouteDialog(), Fix, ActiveNavigationSessionAction, ActiveNavigationSessionState, createRouteSessionCleaner(), NavigationWatcherSession, RemovableSubscription (+24 more)

### Community 8 - "areaFilterMode.ts"
Cohesion: 0.09
Nodes (38): getRadiusRingKm(), ResultsDrawer(), allStationsLimit, AreaCoordinates, distanceOptions, fallbackStationAreaMode, getAreaFilterLabels(), getAreaResultsTitle() (+30 more)

### Community 9 - "siteFeasibilityLogic.ts"
Cohesion: 0.11
Nodes (32): FeasibilityScoreTab(), Metric, styles, TabProps, LocationScoreSummary(), styles, buildingIcon, carIcon (+24 more)

### Community 10 - "ActiveNavigationScreen.tsx"
Cohesion: 0.11
Nodes (28): ActiveNavigationScreen(), connectorLabel(), maneuverIcon(), Props, styles, ChargingStopCard(), buildNavigationMarkers(), Destination (+20 more)

### Community 11 - "areaPrediction.ts"
Cohesion: 0.14
Nodes (27): BUILT_COLOUR, BUILT_LABEL, distributionSummary(), DRAW_LIMIT, drawTruncationNote(), RADIUS_CHOICES, RESEMBLANCE_BANDS, resemblanceBand() (+19 more)

### Community 12 - "AppRoutes.tsx"
Cohesion: 0.09
Nodes (25): evflowIconSource, LoginScreen(), LoginScreenProps, evflowIconSource, ResetPasswordScreen(), ResetPasswordScreenProps, ProfileSelectionRouteProps, ResetPasswordRoute() (+17 more)

### Community 13 - "routeApi.ts"
Cohesion: 0.12
Nodes (27): getEvflowApiBaseUrl(), getAuthHeaders(), checkRouteApiHealth(), createRoutePlan(), deleteRoutePlan(), evaluateActiveRoute(), networkFailure(), parseFailure() (+19 more)

### Community 14 - "competitiveLandscape.ts"
Cohesion: 0.14
Nodes (24): buildGraph(), competitivePressure(), formatDistance(), GraphEdge, GraphNode, MAX_COMPETITORS, Pressure, PRESSURE_MID_KM (+16 more)

### Community 15 - "WalletScreen.tsx"
Cohesion: 0.10
Nodes (26): DetailRowProps, formatCurrency(), formatDate(), formatDetailAmount(), formatSignedCurrency(), formatTime(), formatTopupStatus(), getTransactionIconName() (+18 more)

### Community 16 - "TripSimulationScreen.tsx"
Cohesion: 0.14
Nodes (19): styles, MetricValueText(), MetricValueTextProps, splitMetricValue(), RouteBottomSheet(), RouteBottomSheetProps, styles, styles (+11 more)

### Community 17 - "BusinessDashboardScreen.tsx"
Cohesion: 0.09
Nodes (22): bellIconSvg, buildDonutSvg(), BusinessNavIconName, menuIconSvg, navIconBodies, plusIconSvg, additionalCandidates, BusinessDashboardScreen() (+14 more)

### Community 18 - "plannerApiAdapters.ts"
Cohesion: 0.14
Nodes (22): DensityLegend(), classify(), classOpacity(), DENSITY_CLASSES, DensityScale, formatPeople(), legendRows(), clampUnit() (+14 more)

### Community 19 - "routePlanningLogic.ts"
Cohesion: 0.13
Nodes (24): RouteFieldError(), styles, buildRouteRequest(), canStartNavigation(), ChargingPreference, choiceForPreferences(), clearFieldError(), formatRouteEta() (+16 more)

### Community 20 - "demandHeatmap.ts"
Cohesion: 0.10
Nodes (24): defaultPlannerLayers, DemandPriority, generateMockOptimalSites(), jakartaViewport, OptimalSite, PlannerLayerKey, PlannerLayerState, plannerMarkers() (+16 more)

### Community 21 - "useSiteFeasibilityDetail.ts"
Cohesion: 0.14
Nodes (21): benchmarkStations(), cleanAreaName(), plannerCellToSiteFeasibility(), roadTypeFromNodes(), sumPoi(), benchmark, detail, provenance (+13 more)

### Community 22 - "PeakHoursChart.tsx"
Cohesion: 0.16
Nodes (23): bandColors, chartStyles, formatChartHour(), PeakHoursChart(), PeakHoursChartProps, renderRecommendation(), AvailabilityState, AvailabilityBand (+15 more)

### Community 23 - "apiStationStatus.ts"
Cohesion: 0.13
Nodes (18): backendDaysMondayThroughSunday, buildPeakHourDays(), clamp(), expandConnectors(), getApiStationLiveStatus(), isCount(), isRecord(), isStationOccupancyResponse() (+10 more)

### Community 24 - "expo"
Cohesion: 0.08
Nodes (23): backgroundColor, adaptiveIcon, package, permissions, expo, android, assetBundlePatterns, ios (+15 more)

### Community 25 - "nearbyAlternatives.ts"
Cohesion: 0.12
Nodes (17): AlternativeStation, altStyles, bandTextColors, NearbyAlternatives(), NearbyAlternativesProps, ALTERNATIVES_FETCH_LIMIT, ALTERNATIVES_LIMIT, ALTERNATIVES_RADIUS_KM (+9 more)

### Community 26 - "ConnectorSelectScreen.tsx"
Cohesion: 0.16
Nodes (21): CONNECTOR_OPTIONS, initialsOf(), memberSince(), ProfileScreen(), ProfileScreenProps, styles, ConnectorCard(), ConnectorCardProps (+13 more)

### Community 27 - "TopUpWalletScreen.tsx"
Cohesion: 0.15
Nodes (18): formatCurrency(), formatNumericInput(), parseAmount(), parseTopupIdFromSearch(), TopUpSuccessScreen(), TopUpWalletScreen(), TopUpWalletScreenProps, WalletFlowHeaderProps (+10 more)

### Community 28 - "compilerOptions"
Cohesion: 0.08
Nodes (23): DOM, ES2020, packages/features/src/index.ts, packages/maps/src/index.ts, packages/shared/src/index.ts, packages/ui/src/index.ts, compilerOptions, allowSyntheticDefaultImports (+15 more)

### Community 29 - "aggregateConnectorStatuses.ts"
Cohesion: 0.14
Nodes (16): colors, StationAvailabilitySummary(), StationAvailabilitySummaryProps, summaryStyles, actionStyles, StationDetailActions(), StationDetailActionsProps, aggregateConnectorStatuses() (+8 more)

### Community 30 - "LeafletMap.web.tsx"
Cohesion: 0.12
Nodes (17): downloadReceipt(), generateReceiptHtml(), ReceiptData, escapeHtml(), htmlEscapes, defaultCenter, ensureConnectionAnimationStyle(), LeafletConnectionLine (+9 more)

### Community 31 - "ui/package.json"
Cohesion: 0.09
Nodes (22): dependencies, @evflow/shared, optional, @evflow/shared, expo-location, react, react-native, react-native-webview (+14 more)

### Community 32 - "styles.ts"
Cohesion: 0.12
Nodes (12): ButtonProps, CardProps, FilterPillProps, ScreenProps, buttonStyles, cardStyles, evDriverContainerStyles, filterPillStyles (+4 more)

### Community 33 - "areaFilterSession.ts"
Cohesion: 0.14
Nodes (17): clampDistanceIndex(), FilterDrawer(), defaultDistanceKm, defaultStationAreaMode, DistanceOption, isDistanceOption(), isStationAreaMode(), StationAreaMode (+9 more)

### Community 34 - "location.web.test.ts"
Cohesion: 0.12
Nodes (18): defaultWebLocation, geolocationErrorStatus(), getUserLocation(), LocationPermissionStatus, NavigationFix, NavigationLocationSubscription, BrowserHandle, BrowserOptions (+10 more)

### Community 35 - "features/src/index.ts"
Cohesion: 0.11
Nodes (10): BusinessPlannerEmptyScreenProps, AppRouter(), AppRoutes(), openReceiptPdf(), ReceiptPdfViewer(), ReceiptPdfViewerProps, ReceiptPdfViewerState, styles (+2 more)

### Community 36 - "SavedSitesScreen.tsx"
Cohesion: 0.18
Nodes (20): cleanArea(), getExpandedDetailSheetHeight(), getExpandedListSheetHeight(), getSavedSitesMapView(), jakartaCenter, noPanHandlers, roadType(), SavedSiteCard() (+12 more)

### Community 37 - "FinancialProjectionsTab.tsx"
Cohesion: 0.19
Nodes (17): FinancialProjectionsTab(), formatSessions(), styles, DEMO_PLANNER_ROI_ASSUMPTIONS, getEnergyProjectionCopy(), getPaybackProjectionCopy(), getSessionsProjectionCopy(), getSiteFinancialLifecycleKey() (+9 more)

### Community 38 - "stationDetailState.ts"
Cohesion: 0.18
Nodes (17): availableStationStatusFixture, getMockStationLiveStatus(), occupiedStationStatusFixture, peakDays, weekdayProfiles, CachedStationStatus, getDrawerModeAfterClosingStationDetail(), getFreshCachedStationStatus() (+9 more)

### Community 39 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, expo-camera, @expo-google-fonts/space-grotesk, react, react-dom, @react-native-community/slider, @react-native-picker/picker, react-native-web (+11 more)

### Community 40 - "stations/api.ts"
Cohesion: 0.13
Nodes (15): ApiClientOptions, createApiClient(), QueryParamValue, toQueryString(), EVModelListApiResponse, EVModelListParams, ConnectorTypeApiItem, NearbyStationListParams (+7 more)

### Community 41 - "shared/src/index.ts"
Cohesion: 0.19
Nodes (11): brandOf(), filterVehicleModels(), OTHER_BRAND, ModelCard(), ModelCardProps, modelMeta(), VehicleSelection, VehicleSelectScreen() (+3 more)

### Community 42 - "baseUrl.ts"
Cohesion: 0.22
Nodes (14): getApiBaseUrl, getBundleScriptUrl(), getDevServerHost(), RuntimeGlobal, assertSecureProductionApiBaseUrl(), DEFAULT_EVFLOW_API_BASE_URL, LOCAL_BACKEND_PORT, logDevApiBaseUrl() (+6 more)

### Community 43 - "SvgAssetIcon.tsx"
Cohesion: 0.15
Nodes (12): BookmarkButton(), bookmarkIcon, styles, FilterCategory(), FilterCategoryProps, FilterOption, FilterCategoryProps, FilterOption (+4 more)

### Community 44 - "QuickLoginScreen.tsx"
Cohesion: 0.18
Nodes (11): DEMO_PASSWORD, DemoPersona, DemoPersonaKey, demoPersonas, ensureDemoSession(), getQuickLoginErrorMessage(), PersonaCardProps, QuickLoginScreen() (+3 more)

### Community 45 - "ProfileSelectionScreen.tsx"
Cohesion: 0.16
Nodes (10): rightArrowIcon, icons, RoleAssetIconProps, RoleAssetIcon(), RoleAssetIconProps, ProfileSelectionScreen(), ProfileSelectionScreenProps, RoleCardProps (+2 more)

### Community 46 - "radiusScope.ts"
Cohesion: 0.24
Nodes (14): Bbox, Centre, circleBbox(), clipToRadius(), distanceKm(), formatRadius(), geometryCentre(), RADIUS_DEFAULT_KM (+6 more)

### Community 47 - "NearbyStationsTab.tsx"
Cohesion: 0.21
Nodes (13): getMockNearbyStationPerformance(), getTrendPresentation(), MockNearbyStationPerformance, signedTrend(), stableHash(), TrendPresentation, MetricBox(), NearbyStationsTab() (+5 more)

### Community 48 - "charging/api.ts"
Cohesion: 0.22
Nodes (11): ChargingQuoteApiResponse, fetchChargingQuote(), fetchChargingSession(), fetchChargingSessions(), InsufficientBalanceError, requireAuthHeaders(), settleChargingSession(), startChargingSession() (+3 more)

### Community 49 - "dependencies"
Cohesion: 0.13
Nodes (15): dependencies, @evflow/features, @evflow/maps, @evflow/shared, expo, react-native, @react-native-community/slider, react-router-native (+7 more)

### Community 50 - "RegistrationScreen.tsx"
Cohesion: 0.18
Nodes (11): ModelPicker(), ModelPickerOption, ModelPickerProps, ModelPickerProps, batteryThresholds, defaultConnectorTypes, RegistrationScreen(), RegistrationScreenProps (+3 more)

### Community 51 - "ConnectorAvailabilityRow.tsx"
Cohesion: 0.20
Nodes (12): ConnectorAvailabilityRow(), ConnectorAvailabilityRowProps, formatGroupStatus(), getStatusPill(), rowStyles, StatusPill, useMinuteClock(), closeButtonIcon (+4 more)

### Community 52 - "DestinationSearchModal.tsx"
Cohesion: 0.18
Nodes (8): DestinationSearchModal(), droppedPinLabel(), LocationSearchMode, Props, styles, supportedSuggestionTerms, PickedMapPoint, LatestRequestGate

### Community 53 - "maps/package.json"
Cohesion: 0.14
Nodes (13): dependencies, @evflow/ui, @evflow/ui, react, react-native, main, name, peerDependencies (+5 more)

### Community 54 - "dependencies"
Cohesion: 0.15
Nodes (13): dependencies, @evflow/features, expo-file-system, expo-print, react, react-native-web, react-router, @evflow/features (+5 more)

### Community 55 - "SiteFeasibilitySheet.tsx"
Cohesion: 0.18
Nodes (11): ModelPredictionCard(), Props, styles, getDetailTransitionStyle(), getSheetTransitionStyle(), SiteFeasibilitySheet(), styles, tabs (+3 more)

### Community 56 - "mobile/package.json"
Cohesion: 0.17
Nodes (11): devDependencies, @expo/ngrok, @types/react, typescript, @types/react, typescript, main, name (+3 more)

### Community 57 - "tsconfig.json"
Cohesion: 0.17
Nodes (11): **/vite.config.ts, compilerOptions, noEmit, exclude, extends, include, apps, **/dist (+3 more)

### Community 58 - "scripts"
Cohesion: 0.18
Nodes (11): scripts, build:web, mobile, mobile:android, mobile:ios, mobile:lan, mobile:tunnel, test (+3 more)

### Community 59 - "validation.ts"
Cohesion: 0.36
Nodes (9): formatRupiah(), InitializeChargingScreen(), formatChargingDuration(), formatCurrencyIDR(), getEstimatedChargingMinutes(), REQUIRED_KWH_MAX, REQUIRED_KWH_MIN, validateRequiredKWh() (+1 more)

### Community 60 - "MapView.web.tsx"
Cohesion: 0.31
Nodes (5): MapViewProps, MapView(), MapViewProps, MapMarker, mapViewStyles

### Community 61 - "EVFlow Frontend"
Cohesion: 0.18
Nodes (10): EVFlow Frontend, Install, Mobile Build And Deployment, Prerequisites, Project Structure, Repository, Run Mobile, Run Web (+2 more)

### Community 62 - "mobile/tsconfig.json"
Cohesion: 0.20
Nodes (9): compilerOptions, jsx, noEmit, extends, include, ../../tsconfig.base.json, App.tsx, **/*.ts (+1 more)

### Community 63 - "web/tsconfig.json"
Cohesion: 0.20
Nodes (9): compilerOptions, noEmit, exclude, extends, include, dist, node_modules, src (+1 more)

### Community 64 - "devDependencies"
Cohesion: 0.22
Nodes (9): devDependencies, @types/leaflet, @types/react, @types/react-dom, typescript, @types/react, typescript, @types/leaflet (+1 more)

### Community 65 - "location.ts"
Cohesion: 0.28
Nodes (6): getLocationDialogCopy(), LocationDialogCopy, getUserLocation(), LocationPermissionStatus, NavigationFix, UserLocationResult

### Community 66 - "shared/src/types.ts"
Cohesion: 0.31
Nodes (4): ChargerApiResponse, Charger, ChargerFilter, ChargerStatus

### Community 67 - "web/package.json"
Cohesion: 0.25
Nodes (7): name, private, scripts, build, dev, preview, version

### Community 68 - "package.json"
Cohesion: 0.25
Nodes (7): apps/*, packages/*, name, packageManager, private, version, workspaces

### Community 69 - "overrides"
Cohesion: 0.25
Nodes (8): overrides, esbuild, fast-xml-parser, postcss, send, tar, uuid, @xmldom/xmldom

### Community 70 - "siteFeasibilityLifecycle.test.ts"
Cohesion: 0.25
Nodes (7): breakdownSource, currentDirectory, detailSource, financialTabSource, nearbyTabSource, sheetSource, summarySource

### Community 71 - "features/tsconfig.json"
Cohesion: 0.25
Nodes (7): compilerOptions, jsx, noEmit, extends, include, src, ../../tsconfig.base.json

### Community 72 - "maps/tsconfig.json"
Cohesion: 0.25
Nodes (7): compilerOptions, jsx, noEmit, extends, include, src, ../../tsconfig.base.json

### Community 73 - "ui/tsconfig.json"
Cohesion: 0.25
Nodes (7): compilerOptions, jsx, noEmit, extends, include, src, ../../tsconfig.base.json

### Community 74 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, android, ios, start, start:lan, start:tunnel, web

### Community 75 - "devDependencies"
Cohesion: 0.29
Nodes (7): devDependencies, typescript, vitest, @vitest/coverage-v8, typescript, vitest, @vitest/coverage-v8

### Community 76 - "connectorStatusPalette.ts"
Cohesion: 0.38
Nodes (5): connectorStatusPalette, ConnectorStatusTone, StatusPalette, contrast(), luminance()

### Community 77 - "shared/tsconfig.json"
Cohesion: 0.29
Nodes (6): compilerOptions, noEmit, extends, include, src, ../../tsconfig.base.json

### Community 78 - "generate_components.js"
Cohesion: 0.33
Nodes (5): dir, fs, mapping, path, svgFiles

### Community 79 - "spkluMarkerSvg.ts"
Cohesion: 0.73
Nodes (4): availabilityPip(), badgeInner(), selectedSpkluMarkerSvg(), spkluMarkerSvg()

### Community 80 - "shared/package.json"
Cohesion: 0.33
Nodes (5): main, name, private, types, version

### Community 81 - "App.tsx"
Cohesion: 0.60
Nodes (3): App(), getSpaceGroteskFamily(), installDefaultFont()

### Community 82 - "metro.config.js"
Cohesion: 0.40
Nodes (4): config, { getDefaultConfig }, path, workspaceRoot

### Community 83 - "generate_icons.js"
Cohesion: 0.40
Nodes (4): dir, files, fs, path

### Community 84 - "savedSitesLifecycle.test.ts"
Cohesion: 0.40
Nodes (4): detail, directory, heatmap, screen

### Community 85 - "driverMapIcons.native.ts"
Cohesion: 0.40
Nodes (4): closeButtonIcon, filterSettingIcon, lightningIcon, searchIcon

### Community 86 - "BatteryLevelInput.tsx"
Cohesion: 0.40
Nodes (3): BatteryLevelInputProps, quickValues, styles

### Community 88 - "features/src/vite-env.d.ts"
Cohesion: 0.40
Nodes (4): *.css, *.png, *.svg, *.svg?raw

## Knowledge Gaps
- **595 isolated node(s):** `name`, `slug`, `version`, `orientation`, `scheme` (+590 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **38 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `dependencies` connect `dependencies` to `ui/src/index.ts`, `package.json`, `expo`, `expo-font`, `react-native`, `react-native-webview`, `react-router-dom`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `html5-qrcode` connect `ui/src/index.ts` to `dependencies`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `ScanSpkluScreen()` connect `ui/src/index.ts` to `AppRoutes.tsx`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **What connects `name`, `slug`, `version` to the rest of the system?**
  _595 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `ui/src/index.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.09948979591836735 - nodes in this community are weakly interconnected._
- **Should `peerDependencies` be split into smaller, more focused modules?**
  _Cohesion score 0.04081632653061224 - nodes in this community are weakly interconnected._
- **Should `HelpDeskScreen.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.0935374149659864 - nodes in this community are weakly interconnected._