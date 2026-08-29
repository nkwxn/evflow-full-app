import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  LayoutAnimation,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  UIManager,
  View,
  useWindowDimensions,
  type ViewStyle
} from 'react-native';
import {
  driverMapStyles as mapStyles,
  LeafletMap,
  type LeafletMapMarker,
  type LeafletPointLayer,
  type LeafletPolygonLayer,
  type MapViewport
} from '@evflow/ui';
import {
  fetchPlannerAreaPrediction, fetchPlannerCandidates, fetchPlannerCells, fetchPlannerLandUse,
  fetchPlannerPois, fetchStations
} from '@evflow/shared';
import { PLANNER_LANDUSE_CLASSES } from '@evflow/shared';
import type { PlannerLandUseResponse } from '@evflow/shared';
import { AreaPredictionCard } from './site-prediction/AreaPredictionCard';
import {
  BUILT_COLOUR, RESEMBLANCE_BANDS, SUITABILITY_BANDS, suitabilityKeyNote
} from './site-prediction/areaPrediction';
import type { SuitabilityScale } from './site-prediction/areaPrediction';
import { useAreaPrediction } from './site-prediction/useAreaPrediction';
import { RADIUS_CHOICES } from './site-prediction/areaPrediction';
import { plannerConnectionLines } from './site-connection/connectionLines';
import { formatPeople, legendRows, type DensityScale } from './density/densityScale';
import {
  legendMaxHeight, LEGEND_MAX_WIDTH, legendPillLabel, shouldCollapseLegends
} from './legend/legendLayout';
import {
  RADIUS_DEFAULT_KM, RADIUS_MAX_KM, RADIUS_MIN_KM, RADIUS_STEP_KM,
  circleBbox, clipToRadius, formatRadius, geometryCentre
} from './radius/radiusScope';
import { PlatformSlider } from '../shared/PlatformSlider';
import {
  TRAFFIC_EMPTY_NOTE, TRAFFIC_LEGEND, tomtomKey, trafficOverlay
} from './traffic/tomtomTraffic';

/**
 * Population Density's fill.
 *
 * Magenta, not the purple Model Prediction uses. They were the same #7C3AED, so
 * with both layers on there was no way to tell which shading was which. Nothing
 * else on the map is magenta: the heatmap is red/amber/green, prediction is
 * purple, land use is blue/slate/violet/orange, built cells are slate.
 */
const POPULATION_COLOUR = '#BE185D';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import { closeButtonIcon, filterSettingIcon, searchIcon } from '../ev_driver/components/driverMapIcons';
import { getDrawerAwareMapCenter } from '../ev_driver/station-status/stationDetailState';
import { getUserLocation } from '../ev_driver/utils/location';
import {
  commercialPoiIcon,
  currentLocationIcon,
  heatmapLayerIcon,
  landUseIcon,
  trafficIcon,
  layersIcon,
  optimalSiteIcon,
  populationIcon,
  spkluLayerIcon
} from './demandHeatmapIcons';
import {
  defaultPlannerLayers,
  jakartaViewport,
  plannerMarkers,
  poiPoints,
  plannerPolygons,
  type OptimalSite,
  type PlannerLayerKey,
  type PlannerLayerState
} from './demandHeatmap';
import {
  plannerCandidateToOptimalSite,
  plannerCellsToMetricPolygons,
  plannerPredictionsToPolygons,
  landUseColors,
  plannerLandUsePolygons,
  plannerStationsToMarkers,
  plannerViewportBbox,
  type PlannerLandUseMetric
} from './plannerApiAdapters';
import { SiteFeasibilitySheet } from './site-feasibility/SiteFeasibilitySheet';
import { resolveOptimalSite } from './site-feasibility/siteFeasibilityLogic';
import { plannerErrorCopy, useSiteFeasibilityDetail } from './site-feasibility/useSiteFeasibilityDetail';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

type DemandHeatmapScreenProps = {
  bottomOffset?: number;
  topInset?: number;
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

type PlannerSheetMode = 'layers' | 'site-feasibility';

type LayerRow = {
  icon: string;
  key: PlannerLayerKey;
  subtitle: string;
  title: string;
};

const collapsedSheetHeight = 104;
const collapsedSiteSheetHeight = 258;
const siteDetailZoom = 15;
const sheetAnimation = LayoutAnimation.Presets.easeInEaseOut;

// Four real district centroids, used as search shortcuts and as the opening
// view. Named `mockLocations` until now, which put a gazetteer on every
// mock-data audit's list and hid the entries that were actually invented.
const searchShortcuts: Record<string, Coordinates> = {
  jakarta: { latitude: -6.1754, longitude: 106.8272 },
  'south jakarta': { latitude: -6.2615, longitude: 106.8106 },
  'central jakarta': { latitude: -6.1865, longitude: 106.8341 },
  'west jakarta': { latitude: -6.1683, longitude: 106.7588 }
};

const layerRows: LayerRow[] = [
  { key: 'optimalSites', icon: optimalSiteIcon, title: 'Optimal Sites', subtitle: 'Tap a place · same score as the heatmap' },
  { key: 'demandHeatmap', icon: heatmapLayerIcon, title: 'Demand Heatmap', subtitle: 'Trained model' },
  { key: 'existingSpklus', icon: spkluLayerIcon, title: 'Existing SPKLUs', subtitle: 'Active Network' },
  { key: 'commercialPois', icon: commercialPoiIcon, title: 'Commercial POIs', subtitle: 'Activity Density' },
  { key: 'populationDensity', icon: populationIcon, title: 'Population Density', subtitle: 'Census Data' },
  { key: 'landUse', icon: landUseIcon, title: 'Land Use', subtitle: 'Grid & Land Use' },
  { key: 'liveTraffic', icon: trafficIcon, title: 'Live Traffic', subtitle: 'TomTom · real-time' }
];

export function DemandHeatmapScreen({ bottomOffset = 0, topInset = 0 }: DemandHeatmapScreenProps) {
  const { height, width } = useWindowDimensions();
  // Same breakpoint BusinessPlannerContainer uses to swap the bottom tab bar for
  // a sidebar. Past it the layer panel docks to the right instead of covering
  // the map from below: a full-width bottom sheet is a phone pattern, and on a
  // wide screen it stretches seven toggles across 1,700px while leaving the map
  // a strip too thin to read.
  const dockedPanel = width >= 768;
  const [layers, setLayers] = useState<PlannerLayerState>(defaultPlannerLayers);
  const [expanded, setExpanded] = useState(false);
  // Closed by default on a phone. An open key there covers the map it explains,
  // and a planner who has just tapped a layer on wants to see the layer first.
  const [legendsOpen, setLegendsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [viewport, setViewport] = useState<MapViewport>(jakartaViewport);
  const [center, setCenter] = useState<Coordinates>(searchShortcuts.jakarta);
  const [mapZoom, setMapZoom] = useState(jakartaViewport.zoom);
  const [currentLocation, setCurrentLocation] = useState<Coordinates | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(true);
  const [heatmapUpdating, setHeatmapUpdating] = useState(true);
  // Empty, not seeded. There is nothing honest to show before the planner has
  // said which place they mean, and a fabricated pin left on screen after a
  // failed request reads exactly like a real recommendation.
  const [sites, setSites] = useState<OptimalSite[]>([]);
  // Empty, for the same reason `sites` is. This used to seed five hardcoded
  // red/amber/green rectangles over Jakarta, which rendered on every toggle of
  // the layer and stayed on screen indefinitely when the first fetch failed --
  // fabricated zones that look exactly like a model result.
  const [demandPolygons, setDemandPolygons] = useState<LeafletPolygonLayer[]>([]);
  // Carried out of the fetch so the legend is drawn from the same numbers the
  // cells were painted with. Read from a constant, the two would drift apart the
  // first time the model was retrained and the floors moved.
  const [demandScale, setDemandScale] = useState<
    { suitability: SuitabilityScale | null; ceiling: number | null; built: number } | null>(null);
  const [existingSpkluMarkers, setExistingSpkluMarkers] = useState<LeafletMapMarker[]>([]);
  const [commercialPoiPoints, setCommercialPoiPoints] = useState<LeafletPointLayer[]>([]);
  const [populationPolygons, setPopulationPolygons] = useState<LeafletPolygonLayer[]>([]);
  // Kept beside the polygons because the colours are relative to the current
  // view. Without the values at each break the planner can see which cells are
  // denser but not by how much, and a relative scale with no numbers is the one
  // way this layer could still mislead.
  const [populationScale, setPopulationScale] = useState<DensityScale | null>(null);
  const [landUsePolygons, setLandUsePolygons] = useState<LeafletPolygonLayer[]>([]);
  // Kept so the legend lists the classes actually on screen and can say what
  // blank ground means. Cleared with the layer, like populationScale.
  const [landUseCoverage, setLandUseCoverage] = useState<PlannerLandUseResponse | null>(null);
  const [layerStatus, setLayerStatus] = useState<string | null>(null);
  const [sheetMode, setSheetMode] = useState<PlannerSheetMode>('layers');
  const [selectedSite, setSelectedSite] = useState<OptimalSite | null>(null);
  // Where the planner asked about, not where the map happens to be pointing. A
  // viewport moves when they resize the window; a circle around a chosen point
  // does not, so two places can be compared.
  const [analysisCentre, setAnalysisCentre] = useState<Coordinates | null>(null);
  const [analysisRadiusKm, setAnalysisRadiusKm] = useState<number>(RADIUS_DEFAULT_KM);

  // Scored when asked for, not read from a precomputed layer: the whole grid
  // measures at roughly 155 ms server-side, so freezing predictions in advance
  // buys no speed and goes stale invisibly after a POI reload. Suspended while a
  // site sheet is open, because that sheet asks about one cell and re-scoring
  // the circle behind it is work nobody is looking at.
  // What every layer fetches. Before a point is chosen this is the viewport, so
  // the heatmap can show the planner where to click. After, it is the circle's
  // bounding box, which for a 3 km radius is about 140 cells against 5,242 for a
  // Jakarta viewport. The corners of that box are trimmed off per layer by
  // clipToRadius; see radius/radiusScope for why the clip is not done in SQL.
  const layerBounds = useMemo(() => (analysisCentre
    ? { ...circleBbox(analysisCentre, analysisRadiusKm), zoom: viewport.zoom }
    : viewport), [analysisCentre, analysisRadiusKm, viewport]);

  // Cells arrive as polygons with no centre of their own, so the clip works out
  // where each one sits from its ring. A cell whose geometry cannot be read is
  // dropped rather than drawn: inside the circle by accident is not inside it.
  // Read once: it is a build-time value and cannot change while the app runs.
  const trafficKey = useMemo(
    () => tomtomKey((import.meta as unknown as { env?: Record<string, string | undefined> }).env),
    []);
  // Raster tiles, so this is the one layer the radius cannot clip: TomTom serves
  // whole map squares, not features we can filter. It covers the viewport even
  // when a circle is set, and that is a limit of the format rather than a
  // decision. The circle stays drawn on top, so what is inside it is still clear.
  const trafficOverlays = useMemo(() => {
    const overlay = layers.liveTraffic ? trafficOverlay(trafficKey) : null;
    return overlay ? [overlay] : [];
  }, [layers.liveTraffic, trafficKey]);

  // Hidden rather than shown-and-broken when there is no key. A toggle that
  // turns on nothing is worse than an absent one.
  const visibleLayerRows = useMemo(
    () => layerRows.filter((row) => row.key !== 'liveTraffic' || trafficKey),
    [trafficKey]);

  const clipCells = useCallback(<T extends { features: Array<{ geometry: { type: string; coordinates: unknown } }> }>(
    response: T
  ): T => (analysisCentre
    ? {
        ...response,
        features: clipToRadius(response.features, analysisCentre, analysisRadiusKm,
          (feature) => geometryCentre(feature.geometry))
      }
    : response), [analysisCentre, analysisRadiusKm]);

  const areaPrediction = useAreaPrediction(
    analysisCentre, analysisRadiusKm, layers.demandHeatmap && !selectedSite);
  const selectedSiteId = selectedSite?.id ?? null;
  const detail = useSiteFeasibilityDetail(selectedSiteId, { onMessage: setStatus });
  const expandedRef = useRef(expanded);
  const sheetModeRef = useRef(sheetMode);
  const sheetScrollAtTopRef = useRef(true);
  const lastMapViewRef = useRef({
    center: searchShortcuts.jakarta,
    viewport: jakartaViewport,
    zoom: jakartaViewport.zoom
  });

  useEffect(() => {
    expandedRef.current = expanded;
  }, [expanded]);

  useEffect(() => {
    sheetModeRef.current = sheetMode;
  }, [sheetMode]);

  // Suggestions for the circle the planner chose, not for all of Jabodetabek.
  //
  // The region-wide search is still there in the API, and it is the right answer
  // for "the best places anywhere". It was the wrong thing to open the dashboard
  // with: fifteen pins scattered across Jabodetabek state an answer before
  // anyone has said which place they care about.
  //
  // The score behind each pin is still computed over the whole region, so 0.67
  // in Sudirman and 0.73 in Serpong mean the same thing. Only the search area
  // narrowed.
  useEffect(() => {
    // Selecting a suggestion pauses refetching, it does not erase the
    // suggestions. Clearing them here wiped every pin at the moment one was
    // pressed, so the sheet described a site whose marker had just vanished.
    if (selectedSite) return undefined;
    if (!layers.optimalSites || !analysisCentre) {
      setSites([]);
      return undefined;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => {
      setAnalyzing(true);
      void fetchPlannerCandidates({
        // The same number the heatmap paints, so a numbered pin and the colour
        // under it are one claim. The API falls back to the weighted score when
        // no model is loaded, and says so in `basis`.
        basis: 'suitability',
        centre: {
          latitude: analysisCentre.latitude,
          longitude: analysisCentre.longitude,
          radiusKm: analysisRadiusKm
        },
        signal: controller.signal
      })
        .then((response) => {
          if (controller.signal.aborted) return;
          setSites(response.candidates.map(plannerCandidateToOptimalSite));
          setStatus((current) => current?.startsWith('Planning API:') ? null : current);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || (error as Error)?.name === 'AbortError') return;
          // Cleared rather than left standing. A stale pin under a fresh error
          // message reads as a recommendation for the place now selected.
          setSites([]);
          setStatus(`Planning API: ${plannerErrorCopy(error)} No suggestions for this area.`);
        })
        .finally(() => {
          if (!controller.signal.aborted) setAnalyzing(false);
        });
    }, 400);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [analysisCentre, analysisRadiusKm, layers.optimalSites, selectedSite]);

  // The heatmap is the MODEL's answer now, not the weighted criteria score.
  //
  // It used to colour cells by score = 0.35*coverage + 0.35*population +
  // 0.20*activity + 0.10*roads, a formula with no learning in it. The same
  // endpoint the Model Prediction layer uses takes a bbox as well as a circle,
  // so the viewport-wide behaviour survives the swap: pan and the whole visible
  // grid is scored, exactly as before.
  //
  // Two requests, not one: predict.area returns the values and cells.geojson
  // returns the geometry to paint them on. The prediction is what changed; the
  // geometry request is the same one this effect always made.
  useEffect(() => {
    if (!layers.demandHeatmap || selectedSite) return;

    const controller = new AbortController();
    setHeatmapUpdating(true);
    const timer = setTimeout(() => {
      const bbox = [layerBounds.west, layerBounds.south,
                    layerBounds.east, layerBounds.north].join(',');
      void Promise.all([
        fetchPlannerAreaPrediction({ bbox, limit: 10_000, top: 10_000, signal: controller.signal }),
        fetchPlannerCells({ ...layerBounds, limit: 10_000, metric: 'score', signal: controller.signal })
      ])
        .then(([prediction, response]) => {
          const scale = { suitability: prediction.distribution.suitability_scale,
                          resemblanceCeiling: prediction.distribution.resemblance_ceiling };
          setDemandPolygons(plannerPredictionsToPolygons(
            prediction.predictions, clipCells(response), scale));
          setDemandScale({ suitability: scale.suitability,
                           ceiling: prediction.distribution.resemblance_ceiling,
                           built: prediction.distribution.cells_with_station });
          setStatus(response.truncated
            ? `Planning API: Showing ${response.cells_returned.toLocaleString()} highest-scoring of ${response.cells_in_viewport.toLocaleString()} cells. Zoom in for full coverage.`
            : null);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setStatus(`Planning API: ${plannerErrorCopy(error)} Keeping the previous heatmap.`);
        })
        .finally(() => {
          if (!controller.signal.aborted) setHeatmapUpdating(false);
        });
    }, 280);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [clipCells, layerBounds, layers.demandHeatmap, selectedSite]);

  useEffect(() => {
    if (!layers.existingSpklus || selectedSite) return;

    let active = true;
    const timer = setTimeout(() => {
      void fetchStations({ bbox: plannerViewportBbox(layerBounds), limit: 1000 })
        .then((response) => {
          if (!active) return;
          setExistingSpkluMarkers(plannerStationsToMarkers(
            clipToRadius(response.items, analysisCentre, analysisRadiusKm,
              (station) => ({ latitude: station.latitude, longitude: station.longitude }))));
          setLayerStatus(response.total > response.items.length
            ? `Existing SPKLUs: showing ${response.items.length.toLocaleString()} of ${response.total.toLocaleString()} stations in view.`
            : null);
        })
        .catch(() => {
          if (active) setLayerStatus('Existing SPKLUs could not be loaded for this area.');
        });
    }, 280);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [analysisCentre, analysisRadiusKm, layerBounds, layers.existingSpklus, selectedSite]);

  // Every POI as its own point, drawn on a canvas.
  //
  // Two earlier attempts replaced the points with an aggregate — labelled
  // clusters, then a density surface — because 27,114 DOM markers is unusable.
  // Both answered a question nobody asked: the clutter came from the LABELS on
  // the clusters, not from the points. Small unlabelled dots at this density
  // form the same density picture while staying individually identifiable, and
  // canvas rendering removes the performance reason to aggregate at all.
  useEffect(() => {
    if (!layers.commercialPois || selectedSite) {
      setCommercialPoiPoints([]);
      return undefined;
    }
    const controller = new AbortController();
    fetchPlannerPois({ ...layerBounds, limit: 40_000, signal: controller.signal })
      .then((res) => {
        setCommercialPoiPoints(poiPoints(clipToRadius(
          res.features, analysisCentre, analysisRadiusKm,
          (f) => ({ latitude: f.geometry.coordinates[1], longitude: f.geometry.coordinates[0] }))));
        const total = Object.values(res.pois_in_viewport).reduce((a, b) => a + b, 0);
        setLayerStatus(res.pois_returned < total
          ? `${res.pois_returned.toLocaleString()} of ${total.toLocaleString()} POIs shown. Zoom in for the rest.`
          : `${total.toLocaleString()} POIs shown. Hover a point for its name.`);
      })
      .catch((error: unknown) => {
        if ((error as Error)?.name === 'AbortError') return;
        setLayerStatus('Commercial POIs could not be loaded for this area.');
      });
    return () => controller.abort();
  }, [layers.commercialPois, selectedSite, viewport]);

  useEffect(() => {
    if (!layers.populationDensity || selectedSite) {
      // Cleared with the layer: a legend describing a surface that is no longer
      // drawn is the same class of bug as the orphaned site sheet.
      setPopulationScale(null);
      return undefined;
    }
    return loadMetricLayer({
      clip: clipCells,
      color: POPULATION_COLOUR,
      idPrefix: 'population',
      metric: 'population',
      onError: () => setLayerStatus('Population density could not be loaded for this area.'),
      onLoad: (polygons, scale) => {
        setPopulationPolygons(polygons);
        setPopulationScale(scale);
        setLayerStatus(null);
      },
      viewport: layerBounds
    });
  }, [clipCells, layerBounds, layers.populationDensity, selectedSite]);

  // Shapes, not shaded squares.
  //
  // This used to fetch four per-cell SHARE layers and blend them into one tint
  // per 500 m cell, so a city block and the road beside it came out the same
  // colour and no legend could name what a colour meant. The polygons those
  // shares were measured from now live in planning_landuse, so the layer draws
  // the land itself.
  useEffect(() => {
    if (!layers.landUse || selectedSite) {
      setLandUseCoverage(null);
      return undefined;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => {
      void fetchPlannerLandUse({ ...layerBounds, limit: 6_000, signal: controller.signal })
        .then((response) => {
          setLandUsePolygons(plannerLandUsePolygons(response));
          setLandUseCoverage(response);
          setLayerStatus(response.truncated
            ? `Land use: showing the ${response.polygons_returned.toLocaleString()} largest of `
              + `${response.polygons_in_viewport.toLocaleString()} polygons. Zoom in for the rest.`
            : null);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || (error as Error)?.name === 'AbortError') return;
          setLayerStatus('Land-use coverage could not be loaded for this area.');
        });
    }, 280);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [clipCells, layerBounds, layers.landUse, selectedSite]);

  const animateNext = useCallback(() => {
    LayoutAnimation.configureNext(sheetAnimation);
  }, []);

  const setSheetExpanded = useCallback((nextExpanded: boolean) => {
    animateNext();
    setExpanded(nextExpanded);
  }, [animateNext]);

  const closeSiteFeasibility = useCallback(() => {
    const previousMapView = lastMapViewRef.current;
    sheetModeRef.current = 'layers';
    animateNext();
    setSelectedSite(null);
    setSheetMode('layers');
    setExpanded(false);
    setCenter(previousMapView.center);
    setMapZoom(previousMapView.zoom);
    setViewport(previousMapView.viewport);
  }, [animateNext]);

  // A site sheet outlives the layer that produced it otherwise: turn Optimal
  // Sites off with a suggestion open and the pin disappears from the map while
  // "Loading site analysis..." keeps spinning over it, describing something no
  // longer on screen. Same when the analysis point is cleared: the suggestion
  // belonged to that circle.
  useEffect(() => {
    if (!selectedSite) return;
    if (!layers.optimalSites || !analysisCentre) closeSiteFeasibility();
  }, [analysisCentre, closeSiteFeasibility, layers.optimalSites, selectedSite]);

  const openLayers = useCallback(() => {
    sheetModeRef.current = 'layers';
    animateNext();
    setSelectedSite(null);
    setSheetMode('layers');
    setExpanded(true);
  }, [animateNext]);

  const drawerPanResponder = useMemo(
    () => PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => {
        const isSwipingDown = gestureState.dy > 8;
        const isSwipingUp = gestureState.dy < -8;

        if (expandedRef.current) {
          return isSwipingDown && sheetScrollAtTopRef.current;
        }

        return isSwipingDown || isSwipingUp;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 18 && sheetModeRef.current === 'site-feasibility') {
          setSheetExpanded(false);
        } else if (gestureState.dy > 18 && expandedRef.current) {
          setSheetExpanded(false);
        } else if (gestureState.dy < -18 && !expandedRef.current) {
          setSheetExpanded(true);
        }
      }
    }),
    [setSheetExpanded]
  );

  const onViewportChange = useCallback((next: MapViewport) => {
    setViewport(next);
    if (sheetModeRef.current === 'layers') {
      lastMapViewRef.current = {
        center: next.center ?? {
          latitude: (next.north + next.south) / 2,
          longitude: (next.east + next.west) / 2
        },
        viewport: next,
        zoom: next.zoom
      };
    }
  }, []);

  const onMarkerPress = useCallback((markerId: string) => {
    const site = resolveOptimalSite(sites, markerId);
    if (!site) return;

    // Freeze the return viewport synchronously. Leaflet may auto-pan an open
    // marker popup before React commits the sheet-mode state; waiting for the
    // effect would accidentally save that detail movement as the user's view.
    sheetModeRef.current = 'site-feasibility';
    animateNext();
    setSelectedSite(site);
    setSheetMode('site-feasibility');
    setExpanded(true);
  }, [animateNext, sites]);

  const submitSearch = () => {
    const match = searchShortcuts[query.trim().toLowerCase()];

    if (match) {
      setCenter(match);
      setStatus(null);
    } else if (query.trim()) {
      setStatus('No mock location found. Map unchanged.');
    }
  };

  const locate = async () => {
    setStatus(null);
    const result = await getUserLocation({ requestPermission: true });

    if (result.coordinates) {
      setCurrentLocation(result.coordinates);
      setCenter(result.coordinates);
    } else {
      setStatus('Location unavailable. Staying in Jakarta.');
    }
  };

  const markers = useMemo(
    () => plannerMarkers(layers, sites, existingSpkluMarkers),
    [existingSpkluMarkers, layers, sites]
  );
  // Lines drawn on the map, not in a side panel. Which suggestions belong to
  // the circle you tapped, and once one is selected, what it would be up
  // against. See site-connection/connectionLines for why the two never show at
  // the same time.
  const connectionLines = useMemo(() => plannerConnectionLines({
    centre: analysisCentre,
    sites: layers.optimalSites ? sites : [],
    selected: selectedSite,
    stations: detail.data?.nearbyStations ?? []
  }), [analysisCentre, detail.data, layers.optimalSites, selectedSite, sites]);

  const polygons = useMemo(() => plannerPolygons(layers, {
    demandHeatmap: demandPolygons,
    landUse: landUsePolygons,
    populationDensity: populationPolygons
  }), [areaPrediction.polygons, demandPolygons, landUsePolygons, layers, populationPolygons]);
  const expandedSheetHeight = getExpandedSheetHeight(height, topInset, bottomOffset);
  const sheetHeight = expanded ? expandedSheetHeight : collapsedSheetHeight;
  const expandedSiteSheetHeight = getSiteExpandedSheetHeight(height, width, topInset, bottomOffset);
  const siteSheetHeight = expanded ? expandedSiteSheetHeight : collapsedSiteSheetHeight;

  useEffect(() => {
    if (sheetMode !== 'site-feasibility' || !selectedSite) return;

    setCenter(getDrawerAwareMapCenter(
      selectedSite,
      siteDetailZoom,
      bottomOffset + siteSheetHeight
    ));
    setMapZoom(siteDetailZoom);
  }, [bottomOffset, selectedSite, sheetMode, siteSheetHeight]);

  return (
    <View style={mapStyles.page}>
      <LeafletMap
        center={center}
        currentLocation={currentLocation}
        markers={markers}
        onMapPress={(latitude, longitude) => setAnalysisCentre({ latitude, longitude })}
        onMarkerPress={onMarkerPress}
        onPickedPointMoved={(latitude, longitude) => setAnalysisCentre({ latitude, longitude })}
        onViewportChange={onViewportChange}
        pickedPoint={analysisCentre}
        pointLayers={commercialPoiPoints}
        connectionLines={connectionLines}
        tileOverlays={trafficOverlays}
        polygonLayers={polygons}
        radiusKm={analysisCentre ? analysisRadiusKm : null}
        selectedMarkerId={selectedSite?.id ?? null}
        zoom={mapZoom}
      />

      <View style={[
        mapStyles.searchBar,
        plannerStyles.searchBarCompact,
        dockedPanel ? plannerStyles.searchBarDocked : null,
        { top: 16 + topInset }
      ]}>
        <View style={mapStyles.searchIcon}>
          <SvgAssetIcon color="#6B7A7B" height={18} name="search" svg={searchIcon} width={18} />
        </View>
        <TextInput
          accessibilityLabel="Search location"
          onChangeText={setQuery}
          onSubmitEditing={submitSearch}
          placeholder="Search location..."
          placeholderTextColor="#819097"
          returnKeyType="search"
          style={[mapStyles.searchInput, plannerStyles.searchInputCompact]}
          value={query}
        />
        <Pressable
          accessibilityLabel="Open map layers"
          accessibilityRole="button"
          onPress={openLayers}
          style={mapStyles.filterIcon}
        >
          <SvgAssetIcon color="#005F64" height={18} name="filter" svg={filterSettingIcon} width={18} />
        </Pressable>
      </View>

      <View style={[plannerStyles.mapControls, { top: topInset + 104 }]}>
        <MapControlButton
          accessibilityLabel="Use current location"
          icon={currentLocationIcon}
          onPress={() => void locate()}
        />
        <MapControlButton
          accessibilityLabel="Open map layers"
          icon={layersIcon}
          onPress={openLayers}
          primary
        />
      </View>

      {status || layerStatus ? (
        <Text accessibilityLiveRegion="polite" style={[plannerStyles.status, { top: topInset + 140 }]}>
          {layerStatus ?? status}
        </Text>
      ) : null}

      {analyzing && layers.optimalSites ? (
        <View style={[plannerStyles.analysis, { top: topInset + 140 }]}>
          <ActivityIndicator color="#006973" size="small" />
          <Text style={plannerStyles.analysisText}>Analyzing visible area...</Text>
        </View>
      ) : null}

      {heatmapUpdating && layers.demandHeatmap && !analyzing ? (
        <View style={[plannerStyles.analysis, { top: topInset + 140 }]}>
          <ActivityIndicator color="#006973" size="small" />
          <Text style={plannerStyles.analysisText}>Updating analysis...</Text>
        </View>
      ) : null}

      {/* One stack, laid out by flex. Each legend used to position itself with a
          hand-added offset for whichever others happened to be on, and with
          three live those guesses overlapped. Here the container owns the
          spacing, so a legend growing a row cannot collide with anything. */}
      {sheetMode === 'layers' ? (() => {
        const keys = [
          layers.liveTraffic && trafficKey ? <TrafficLegend key="traffic" /> : null,
          layers.populationDensity && populationScale ? (
            <DensityLegend
              colour={POPULATION_COLOUR}
              key="density"
              scale={populationScale}
              title="PEOPLE PER CELL"
            />
          ) : null,
          layers.landUse && landUseCoverage ? (
            <LandUseLegend coverage={landUseCoverage} key="landuse" />
          ) : null,
          // `!expanded` alone hid this on desktop, where opening Map Layers sets
          // expanded and the docked panel leaves the map fully visible beside
          // it — so the one layer whose colours cannot be guessed lost its key
          // exactly when someone opened the panel to find out what they meant.
          // On a phone the expanded sheet really does cover the map, so the
          // legend still stands down there.
          layers.demandHeatmap && (dockedPanel || !expanded) && demandScale ? (
            <ModelPredictionLegend
              builtCells={demandScale.built}
              ceiling={demandScale.ceiling}
              key="demand"
              suitability={demandScale.suitability}
              title="DEMAND HEATMAP"
            />
          ) : null
        ].filter(Boolean);
        const bottom = dockedPanel ? bottomOffset + 16
                                   : bottomOffset + collapsedSheetHeight + 12;
        if (!shouldCollapseLegends(width, keys.length)) {
          return <View style={[plannerStyles.legendStack, { bottom }]}>{keys}</View>;
        }
        // Phone. Closed, one pill naming how many layers are keyed; open, the
        // same cards inside a capped scroll area so they can never grow past the
        // map again however many rows a legend gains.
        return (
          <View style={[plannerStyles.legendStack, { bottom }]}>
            {legendsOpen ? (
              <ScrollView
                showsVerticalScrollIndicator={false}
                style={[plannerStyles.legendScroll, { maxHeight: legendMaxHeight(height) }]}
              >
                <View style={plannerStyles.legendScrollInner}>{keys}</View>
              </ScrollView>
            ) : null}
            <Pressable
              accessibilityLabel={legendsOpen ? 'Hide map key' : 'Show map key'}
              accessibilityRole="button"
              onPress={() => setLegendsOpen((v) => !v)}
              style={plannerStyles.legendPill}
            >
              <Text style={plannerStyles.legendPillText}>
                {legendsOpen ? 'Hide key' : legendPillLabel(keys.length)}
              </Text>
            </Pressable>
          </View>
        );
      })() : null}

      {/* Docked, the panel is present or it is not: fading its contents to zero
          while a 360px white slab stays over the map would be the worst of
          both. On a phone the collapsed sheet still peeks its header, which is
          what makes it draggable back up. */}
      {sheetMode === 'layers' && (!dockedPanel || expanded) ? (
        <View
          style={dockedPanel
            ? [mapStyles.sheet, plannerStyles.sheet, plannerStyles.dockedPanel,
               { bottom: bottomOffset + 16, top: topInset + 74 }]
            : [mapStyles.sheet, plannerStyles.sheet, getSheetStateStyle(sheetHeight),
               { bottom: bottomOffset }]}
          {...(dockedPanel ? {} : drawerPanResponder.panHandlers)}
        >
        {/* The grab handle is a bottom-sheet affordance. A docked panel does not
            slide up and down, so offering the gesture would promise something
            that does nothing. */}
        {dockedPanel ? null : (
        <Pressable
          accessibilityLabel={expanded ? 'Collapse Map Layers' : 'Expand Map Layers'}
          accessibilityRole="button"
          accessibilityState={{ expanded }}
          onPress={() => setSheetExpanded(!expanded)}
          style={mapStyles.drawerHandleWrap}
        >
          <View style={mapStyles.drawerHandle} />
        </Pressable>
        )}

        <View style={mapStyles.drawerBody}>
          <View style={[mapStyles.sheetHeader, plannerStyles.sheetHeader]}>
            <View>
              <Text style={mapStyles.sheetTitle}>Map Layers</Text>
              <Text style={plannerStyles.sheetSubtitle}>Customize map views</Text>
            </View>

            {expanded || dockedPanel ? (
              <Pressable
                accessibilityLabel="Collapse map layers"
                accessibilityRole="button"
                onPress={() => setSheetExpanded(false)}
                style={mapStyles.closeButton}
              >
                <SvgAssetIcon color="#191C1D" height={14} name="close" svg={closeButtonIcon} width={14} />
              </Pressable>
            ) : (
              <Pressable
                accessibilityLabel="Expand map layers"
                accessibilityRole="button"
                onPress={() => setSheetExpanded(true)}
                style={mapStyles.filterButton}
              >
                <SvgAssetIcon color="#4C5960" height={16} name="filter" svg={filterSettingIcon} width={16} />
                <Text style={mapStyles.filterButtonText}>Layers</Text>
              </Pressable>
            )}
          </View>

          <ScrollView
            contentContainerStyle={plannerStyles.layerList}
            onScroll={(event) => {
              sheetScrollAtTopRef.current = event.nativeEvent.contentOffset.y <= 0;
            }}
            scrollEnabled={expanded || dockedPanel}
            scrollEventThrottle={16}
            showsVerticalScrollIndicator={false}
            style={[mapStyles.expandedContent, getExpandedContentStateStyle(expanded || dockedPanel)]}
          >
            {(
              <>
                {/* A slider rather than three fixed choices. Catchment is not a
                    property of the tool, it is a property of the site: a mall on a
                    toll road pulls from further than a kampung street, and 1/3/5
                    made the planner round their question to whichever button was
                    closest. Every layer below reads this same radius. */}
                <View style={plannerStyles.radiusRow}>
                  <Text style={plannerStyles.radiusLabel}>RADIUS</Text>
                  <Text style={plannerStyles.radiusValue}>{formatRadius(analysisRadiusKm)}</Text>
                </View>
                <PlatformSlider
                  maximumValue={RADIUS_MAX_KM}
                  minimumTrackTintColor="#7C3AED"
                  thumbTintColor="#5B21B6"
                  minimumValue={RADIUS_MIN_KM}
                  onValueChange={setAnalysisRadiusKm}
                  step={RADIUS_STEP_KM}
                  value={analysisRadiusKm}
                />
                {analysisCentre ? null : (
                  <Text style={plannerStyles.radiusHint}>
                    Tap the map to place the circle. Until then every layer follows the view.
                  </Text>
                )}
                {layers.demandHeatmap ? (
                <AreaPredictionCard
                  distribution={areaPrediction.distribution}
                  drawnCells={areaPrediction.drawnCells}
                  error={areaPrediction.error}
                  interpretation={areaPrediction.interpretation}
                  loading={areaPrediction.loading}
                  model={areaPrediction.model}
                  utilisationModel={areaPrediction.utilisationModel}
                  radiusKm={analysisRadiusKm}
                />
                ) : null}
              </>
            )}
            {visibleLayerRows.map((row) => (
              <LayerToggleRow
                key={row.key}
                enabled={layers[row.key]}
                row={row}
                onToggle={() => setLayers((current) => ({ ...current, [row.key]: !current[row.key] }))}
              />
            ))}
          </ScrollView>
        </View>
        </View>
      ) : selectedSite ? (
        /* Guarded on the site itself, not only on sheetMode. Those are two
           pieces of state that every close path has to change together, and one
           of them did not: the sheet appeared over an empty map, with no pin, no
           chosen point and every layer off, spinning "Loading site analysis..."
           for a site that was not selected. With siteId null the fetch returns
           immediately and data stays null, which is exactly the condition the
           spinner renders on, so it never resolved and never errored.

           Requiring selectedSite makes that state unreachable rather than
           relying on every path to tidy up after itself. */
        <SiteFeasibilitySheet
          activeTab={detail.activeTab}
          bottom={bottomOffset}
          data={detail.data}
          error={detail.error}
          expanded={expanded}
          financial={detail.financial}
          financialError={detail.financialError}
          financialLoading={detail.financialLoading}
          height={siteSheetHeight}
          interpretation={detail.interpretation}
          isSaved={detail.isSaved}
          isSaving={detail.isSaving}
          loading={detail.loading}
          model={detail.model}
          onClose={closeSiteFeasibility}
          onFinancialRetry={detail.retryFinancial}
          onScrollTopChange={(atTop) => { sheetScrollAtTopRef.current = atTop; }}
          onTabChange={detail.setActiveTab}
          onToggleExpanded={() => setSheetExpanded(!expanded)}
          onToggleSaved={detail.isMock ? undefined : detail.toggleSaved}
          onRetry={detail.retry}
          panHandlers={drawerPanResponder.panHandlers}
          prediction={detail.prediction}
          predictionError={detail.predictionError}
          predictionLoading={detail.predictionLoading}
          regionalCeiling={detail.regionalCeiling}
        />
      ) : null}
    </View>
  );
}

function MapControlButton({
  accessibilityLabel,
  icon,
  onPress,
  primary = false
}: {
  accessibilityLabel: string;
  icon: string;
  onPress: () => void;
  primary?: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      onPress={onPress}
      style={[plannerStyles.mapControlButton, primary && plannerStyles.mapControlButtonPrimary]}
    >
      <SvgAssetIcon height={22} svg={icon} width={22} />
    </Pressable>
  );
}

/**
 * What the shading on the density layer actually means, in people.
 *
 * The classes are quantiles over the cells currently on screen, so the colours
 * are relative to this view rather than absolute. That is the normal trade for a
 * choropleth and it only misleads when the numbers are hidden, which is the
 * whole reason this exists: "darkest = 8,100 people" is a fact a planner can
 * use, "darkest = a lot" is not.
 *
 * Printed densest-first, because the top of the list is what a siting decision
 * turns on.
 */
/**
 * What the coloured roads mean.
 *
 * The only layer that had no legend, and the one whose colours a planner is
 * least likely to already know. Green is deliberately absent: relative-delay
 * paints only roads that differ from free flow, so a road running normally is
 * not drawn at all, and TRAFFIC_EMPTY_NOTE says so rather than leaving an empty
 * layer to be read as a broken one.
 */
function TrafficLegend() {
  return (
    <View style={plannerStyles.legend}>
      <Text style={plannerStyles.legendTitle}>LIVE TRAFFIC</Text>
      {TRAFFIC_LEGEND.map((row) => (
        <View key={row.label} style={plannerStyles.legendRow}>
          <View style={[plannerStyles.legendSwatch, { backgroundColor: row.colour }]} />
          <Text style={plannerStyles.legendText}>{row.label}</Text>
        </View>
      ))}
      <Text style={plannerStyles.legendNote}>{TRAFFIC_EMPTY_NOTE}</Text>
    </View>
  );
}

/**
 * What the squares mean, which nothing on screen said before.
 *
 * Population Density and Live Traffic both carried legends; the model's shading
 * did not, and it is the layer whose colours are least guessable. Until commit
 * f72afdd this layer and Population Density were both #7C3AED, so with the two
 * on there was no way to tell which shading was which -- a planner asked exactly
 * that, and was right to.
 *
 * IT DESCRIBES WHICHEVER SCALE IS ACTUALLY PAINTING
 *
 * With a suitability scale the map is red/amber/green and the pins are ranked on
 * the same number, so the note says so. Without one it falls back to purple
 * resemblance, which answers a different question, and the note changes with it.
 * A legend naming bands the map is not painting is worse than no legend at all,
 * because a legend is believed.
 *
 * RED HERE IS NOT RED ON LIVE TRAFFIC
 *
 * Both layers can be on at once, and on Live Traffic red means congested and
 * bad. The wording never says "high demand" for that reason, and because these
 * are quantile bands: "top 10% of Jabodetabek" is what a quantile supports.
 *
 * Green is the one band that has to be read carefully, so the note spells it
 * out: it includes districts that are already well served. That is the
 * acceptance criterion, and a reader who takes green as "nothing here" has
 * inverted it.
 *
 * Built cells are named rather than left as an unexplained fourth colour: on the
 * resemblance fallback they are the cells the model scores HIGHEST, so a reader
 * who assumes slate means "very good" has inverted that layer too.
 */
function ModelPredictionLegend({ suitability, ceiling, builtCells, title = 'MODEL PREDICTION' }: {
  suitability: SuitabilityScale | null;
  ceiling: number | null;
  builtCells: number;
  title?: string;
}) {
  // The legend follows the shading rather than describing one fixed palette.
  // With a suitability scale the map is red/amber/green; without one it falls
  // back to purple resemblance, and a legend still naming bands the map is not
  // painting is worse than none, because it is believed.
  const bands = suitability
    ? SUITABILITY_BANDS.map((b) => ({ colour: b.colour, label: b.label }))
    : RESEMBLANCE_BANDS.map((b) => ({ colour: b.colour, label: b.label }));
  return (
    <View style={plannerStyles.legend}>
      <Text style={plannerStyles.legendTitle}>{title}</Text>
      {bands.map((band) => (
        <View key={band.colour} style={plannerStyles.legendRow}>
          <View style={[plannerStyles.legendSwatch, { backgroundColor: band.colour }]} />
          <Text style={plannerStyles.legendText}>{band.label}</Text>
        </View>
      ))}
      <View style={plannerStyles.legendRow}>
        <View style={[plannerStyles.legendSwatch, { backgroundColor: BUILT_COLOUR }]} />
        <Text style={plannerStyles.legendText}>
          {builtCells > 0 ? `${builtCells.toLocaleString()} already built` : 'already built'}
        </Text>
      </View>
      <Text style={plannerStyles.legendNote}>
        {suitability
          // Printed from the same floors that chose the fills, so the two cannot
          // drift. Never "high demand": these are quantile bands, and red on this
          // layer sits on the same screen as red on Live Traffic, where it means
          // congested and bad.
          ? suitabilityKeyNote(suitability)
            + ' The numbered pins are ranked on this same score.'
          : ceiling === null
            // No ceiling means no denominator, and a share of an unknown best is
            // not a number to print. Say the scale is unanchored instead.
            ? 'Resembles cells that already have a station. Scale unanchored this time.'
            : `Suitability is unavailable, so this shows RESEMBLANCE — how much a cell looks `
              + `like one that already has a station, which is not a recommendation. `
              + `"Regional best" is ${ceiling.toFixed(2)}, the highest any unbuilt cell in `
              + `Jabodetabek reaches. Numbered circles are Optimal Sites, a different score.`}
      </Text>
    </View>
  );
}

/**
 * A list, not a gradient, because land use is a category and not a quantity.
 *
 * The previous layer shaded each 500 m cell by four blended shares, so its
 * colours could not be listed: a square meant "mostly residential, a bit
 * commercial" and every square meant something slightly different. These are
 * polygons of exactly one class, so the legend is four rows and each row is
 * true everywhere on the map.
 *
 * It lists only the classes PRESENT in this viewport. A legend naming four
 * classes over a screen showing two invites the reader to hunt for colours that
 * are not there.
 *
 * The coverage note is not decoration. Measured 2026-08-25, half of Jabodetabek
 * has no land-use polygon of any class, so blank ground means UNMAPPED, and a
 * planner reading it as open land would be reading the absence of a volunteer's
 * work as a fact about the city.
 */
function LandUseLegend({ coverage }: { coverage: PlannerLandUseResponse }) {
  const present = PLANNER_LANDUSE_CLASSES.filter((c) => coverage.classes.includes(c));
  if (!present.length) return null;
  return (
    <View style={plannerStyles.legend}>
      <Text style={plannerStyles.legendTitle}>LAND USE</Text>
      {present.map((cls) => (
        <View key={cls} style={plannerStyles.legendRow}>
          <View style={[plannerStyles.legendSwatch,
                        { backgroundColor: landUseColors[cls] }]} />
          <Text style={plannerStyles.legendText}>
            {cls.charAt(0).toUpperCase() + cls.slice(1)}
          </Text>
        </View>
      ))}
      <Text style={plannerStyles.legendNote}>
        {coverage.polygons_returned.toLocaleString()} polygons drawn. Unshaded ground is
        unmapped in OpenStreetMap, not empty.
      </Text>
    </View>
  );
}

function DensityLegend({ colour, scale, title }: {
  colour: string;
  scale: DensityScale;
  title: string;
}) {
  const rows = legendRows(scale, formatPeople).slice().reverse();
  return (
    <View style={plannerStyles.legend}>
      <Text style={plannerStyles.legendTitle}>{title}</Text>
      {rows.map((row) => (
        <View key={row.classIndex} style={plannerStyles.legendRow}>
          <View style={[plannerStyles.legendSwatch,
                        { backgroundColor: colour, opacity: row.opacity }]} />
          <Text style={plannerStyles.legendText}>{row.label}</Text>
        </View>
      ))}
      <Text style={plannerStyles.legendNote}>Shading is relative to this view</Text>
    </View>
  );
}


function LayerToggleRow({ enabled, onToggle, row }: { enabled: boolean; onToggle: () => void; row: LayerRow }) {
  return (
    <View style={plannerStyles.layerRow}>
      <View style={[plannerStyles.layerIcon, enabled && plannerStyles.layerIconEnabled]}>
        <SvgAssetIcon height={20} svg={row.icon} width={20} />
      </View>
      <View style={plannerStyles.layerCopy}>
        <Text style={plannerStyles.layerTitle}>{row.title}</Text>
        <Text style={[plannerStyles.layerSubtitle, enabled && plannerStyles.layerSubtitleEnabled]}>{row.subtitle}</Text>
        {/* The three-line explainer that used to sit here said what the
            subtitle already says, and it cost more vertical space than any
            other row on the panel. */}
      </View>
      <Pressable
        accessibilityLabel={`Toggle ${row.title}`}
        accessibilityRole="switch"
        accessibilityState={{ checked: enabled }}
        onPress={onToggle}
        style={[plannerStyles.toggle, enabled && plannerStyles.toggleEnabled]}
      >
        <View style={[plannerStyles.toggleKnob, enabled && plannerStyles.toggleKnobEnabled]} />
      </Pressable>
    </View>
  );
}

/**
 * How tall the layer sheet opens on a phone.
 *
 * Only phones reach this now: past 768px the panel docks to the right instead,
 * so this no longer has to serve a desktop viewport as well.
 *
 * It used to take 68% of the screen with a 360px floor, which on a 844px phone
 * left the map 270px -- about four map labels tall. The point of opening the
 * layer list is to turn something on and watch it appear, and you cannot watch
 * a strip. At 52% the same phone keeps roughly 400px of map, the sheet still
 * shows its header and four rows, and the rest scrolls.
 *
 * The floor stays because a very short viewport should still show more than a
 * title, and the cap stops a tall phone from opening a sheet with empty space
 * under the last row.
 */
function getExpandedSheetHeight(screenHeight: number, topInset: number, bottomOffset: number) {
  // top 16 + minHeight 46 + a 12px gap. Mirrors searchBarCompact; if that
  // changes and this does not, the sheet either overlaps the bar or leaves a
  // band of dead space under it.
  const searchBarBottom = topInset + 16 + 46 + 12;
  const availableHeight = screenHeight - bottomOffset - searchBarBottom;
  const viewportProportion = (screenHeight - bottomOffset) * 0.44;
  return Math.max(280, Math.floor(Math.min(380, availableHeight, viewportProportion)));
}

function getSiteExpandedSheetHeight(screenHeight: number, screenWidth: number, topInset: number, bottomOffset: number) {
  const usableHeight = screenHeight - bottomOffset;
  const roomBelowSearch = usableHeight - (topInset + 102);
  const targetHeight = screenWidth < 768 ? roomBelowSearch : Math.min(720, usableHeight * 0.8, roomBelowSearch);
  return Math.max(collapsedSiteSheetHeight, Math.floor(targetHeight));
}

function loadMetricLayer({
  clip,
  color,
  idPrefix,
  metric,
  onError,
  onLoad,
  viewport
}: {
  clip: <T extends { features: Array<{ geometry: { type: string; coordinates: unknown } }> }>(
    response: T
  ) => T;
  color: string;
  idPrefix: string;
  metric: string;
  onError: () => void;
  onLoad: (polygons: LeafletPolygonLayer[], scale: DensityScale | null) => void;
  viewport: MapViewport;
}) {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    void fetchPlannerCells({ ...viewport, limit: 10_000, metric, signal: controller.signal })
      .then((response) => {
        const { polygons, scale } = plannerCellsToMetricPolygons(clip(response), color, idPrefix);
        onLoad(polygons, scale);
      })
      .catch(() => {
        if (!controller.signal.aborted) onError();
      });
  }, 280);

  return () => {
    clearTimeout(timer);
    controller.abort();
  };
}

type WebTransitionStyle = ViewStyle & {
  transitionDuration?: string;
  transitionProperty?: string;
  transitionTimingFunction?: string;
};

function getSheetStateStyle(height: number): WebTransitionStyle {
  return {
    height,
    ...(Platform.OS === 'web'
      ? {
          transitionDuration: '240ms',
          transitionProperty: 'height',
          transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)'
        }
      : {})
  };
}

function getExpandedContentStateStyle(expanded: boolean): WebTransitionStyle {
  return {
    opacity: expanded ? 1 : 0,
    pointerEvents: expanded ? 'auto' : 'none',
    transform: [{ translateY: expanded ? 0 : 16 }],
    ...(Platform.OS === 'web'
      ? {
          transitionDuration: '180ms',
          transitionProperty: 'opacity, transform',
          transitionTimingFunction: 'ease-out'
        }
      : {})
  };
}

const plannerStyles = StyleSheet.create({
  radiusHint: { color: '#8A979B', fontSize: 11, lineHeight: 16, marginBottom: 6, marginTop: 6 },
  radiusValue: { color: '#5B21B6', fontSize: 13, fontWeight: '700' },
  legendNote: { color: '#8A979B', fontSize: 9, marginTop: 6 },
  legendSwatch: { borderRadius: 2, height: 10, marginRight: 8, width: 14 },
  legendTitle: {
    color: '#8A979B', fontSize: 9, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6
  },
  // The shared searchBar is left:22 right:22 minHeight:66, which on a 1,440px
  // screen is a 1,100px-wide bar 66px tall to hold one short query. Shrunk here
  // rather than in the shared style, which SavedSitesScreen also uses.
  searchBarCompact: {
    borderRadius: 10,
    gap: 10,
    minHeight: 46,
    paddingHorizontal: 14
  },
  // Released from the right edge so it stops under the docked panel instead of
  // running behind it, and capped so it does not stretch across the map.
  searchBarDocked: {
    maxWidth: 420,
    // 'auto', not undefined: StyleSheet.create drops undefined values, so the
    // base style's right:22 would survive and fight the fixed width.
    right: 'auto',
    width: 420
  },
  searchInputCompact: { fontSize: 14, minHeight: 30 },
  dockedPanel: {
    borderBottomLeftRadius: 16,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 0,
    boxShadow: '-4px 0 18px rgba(0, 0, 0, 0.10)',
    // Same trap: with left:undefined the base style's left:0 survived and the
    // panel docked to the LEFT, straight over the search bar. Measured before
    // it was noticed, which is why it is spelled out here.
    left: 'auto',
    // Wide enough for a layer row with its description, narrow enough that the
    // map keeps most of a desktop viewport.
    maxWidth: '38%',
    paddingTop: 18,
    right: 16,
    width: 360
  },
  radiusChip: {
    backgroundColor: '#FFFFFF', borderColor: '#DDE5E7', borderRadius: 14, borderWidth: 1,
    paddingHorizontal: 12, paddingVertical: 5
  },
  radiusChipOn: { backgroundColor: '#EDE9FE', borderColor: '#7C3AED' },
  radiusChipText: { color: '#55656A', fontSize: 12, fontWeight: '600' },
  radiusChipTextOn: { color: '#5B21B6' },
  radiusLabel: { color: '#8A979B', fontSize: 11, fontWeight: '700', letterSpacing: 0.6, marginRight: 4 },
  radiusRow: { alignItems: 'center', flexDirection: 'row', gap: 8, marginBottom: 10 },
  mapControls: {
    gap: 12,
    position: 'absolute',
    right: 22,
    zIndex: 9999
  },
  mapControlButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 24,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.14)',
    height: 48,
    justifyContent: 'center',
    width: 48
  },
  mapControlButtonPrimary: {
    backgroundColor: '#007D8C'
  },
  status: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 8,
    color: '#4B5563',
    left: 22,
    padding: 8,
    position: 'absolute',
    right: 82,
    textAlign: 'center',
    zIndex: 9999
  },
  analysis: {
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 16,
    flexDirection: 'row',
    gap: 8,
    left: 22,
    paddingHorizontal: 12,
    paddingVertical: 8,
    position: 'absolute',
    zIndex: 9999
  },
  analysisText: {
    color: '#355055',
    fontSize: 12,
    fontWeight: '700'
  },
  // No position of its own any more. Legends used to place themselves with
  // hand-computed bottom offsets (+108 for the heatmap, +132 for density), and
  // those constants were guesses: the real height depends on how many rows a
  // legend has and how the font renders. With three legends live they
  // overlapped. They are children of legendStack now, so the layout engine
  // spaces them and no arithmetic can be wrong.
  legend: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 10,
    boxShadow: '0 3px 10px rgba(21,35,38,0.14)',
    gap: 7,
    padding: 10
  },
  legendStack: {
    alignItems: 'flex-start',
    bottom: 0,
    gap: 10,
    left: 14,
    position: 'absolute',
    zIndex: 9999
  },
  // Capped so the cards scroll inside it rather than pushing the pill off screen.
  legendScroll: { borderRadius: 10, maxWidth: LEGEND_MAX_WIDTH },
  legendScrollInner: { alignItems: 'flex-start', gap: 10, paddingBottom: 2 },
  legendPill: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 999,
    boxShadow: '0 3px 10px rgba(21,35,38,0.14)',
    paddingHorizontal: 14,
    paddingVertical: 8
  },
  legendPillText: {
    color: '#364246', fontSize: 12, fontWeight: '700', letterSpacing: 0.2
  },
  legendRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8
  },
  legendDot: {
    borderRadius: 5,
    height: 10,
    width: 10
  },
  legendText: {
    color: '#364246',
    fontSize: 12,
    fontWeight: '600'
  },
  sheet: {
    paddingBottom: 20
  },
  sheetHeader: {
    marginBottom: 0
  },
  sheetSubtitle: {
    color: '#5A6870',
    fontSize: 14,
    marginTop: 2
  },
  layerList: {
    paddingBottom: 8,
    paddingTop: 6
  },
  layerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    // 62 -> 48. With the explainer gone every row is exactly two lines, so the
    // extra height was padding around nothing.
    minHeight: 48,
    paddingVertical: 4
  },
  layerIcon: {
    alignItems: 'center',
    backgroundColor: '#EEF1FF',
    borderRadius: 20,
    height: 34,
    justifyContent: 'center',
    marginRight: 12,
    width: 34
  },
  layerIconEnabled: {
    backgroundColor: '#D5F3FA'
  },
  layerCopy: {
    flex: 1,
    paddingRight: 10
  },
  layerTitle: {
    color: '#1F2937',
    fontSize: 14,
    fontWeight: '800'
  },
  layerSubtitle: {
    color: '#71808A',
    fontFamily: 'monospace',
    fontSize: 11,
    marginTop: 2
  },
  layerSubtitleEnabled: {
    color: '#0077A7'
  },
  helperText: {
    color: '#607077',
    fontSize: 10,
    lineHeight: 13,
    marginTop: 3
  },
  toggle: {
    backgroundColor: '#DBE4FA',
    borderColor: '#B5C1D8',
    borderRadius: 12,
    borderWidth: 1,
    height: 24,
    justifyContent: 'center',
    paddingHorizontal: 2,
    width: 42
  },
  toggleEnabled: {
    backgroundColor: '#007D8C',
    borderColor: '#007D8C'
  },
  toggleKnob: {
    backgroundColor: '#718096',
    borderRadius: 9,
    height: 18,
    width: 18
  },
  toggleKnobEnabled: {
    alignSelf: 'flex-end',
    backgroundColor: '#FFFFFF'
  }
});
