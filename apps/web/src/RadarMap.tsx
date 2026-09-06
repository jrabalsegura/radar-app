import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSourceSpecification,
} from 'maplibre-gl';
import mapLibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { useEffect, useRef, useState } from 'react';
import 'maplibre-gl/dist/maplibre-gl.css';
import { prepareMapImage, removeMapImage } from './mapImage';
import { improvePlaceLabels, firstLabelLayer } from './mapStyle';
import { recordRadarRendered } from './performanceMetrics';
import {
  initialRadarZoom,
  radarCameraCenter,
  radarCameraPadding,
  type RadarCameraInsets,
} from './radarCamera';
import type { RadarIndexEntry, RegionalRadarIndexEntry } from './radarIndex';
import type { LongitudeLatitude } from './radarLocation';
import type { RadarTimelineFrame } from './radarManifest';
setWorkerUrl(mapLibreWorkerUrl);
const DEFAULT_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
const RADAR_IDS = ['regional-frame-a', 'regional-frame-b'] as const;
const DEBUG_SOURCE_ID = 'calibration-debug';
const DEBUG_LAYER_ID = 'coverage-debug';
const NO_COVERAGE_ID = 'no-coverage';
const NOMINAL_ID = 'outside-nominal-coverage';
interface RadarMapProps {
  radar: RadarIndexEntry;
  selectedFrame: RadarTimelineFrame | null;
  opacity: number;
  showDebug: boolean;
  showNoCoverage: boolean;
  reducedMotion: boolean;
  userCoordinates: LongitudeLatitude | null;
  cameraInsets: RadarCameraInsets;
  recenterRequest: number;
  onDisplayedFrame: (frame: RadarTimelineFrame | null) => void;
  onFailedImage: (url: string) => void;
}
export function RadarMap({
  radar,
  selectedFrame,
  opacity,
  showDebug,
  showNoCoverage,
  reducedMotion,
  userCoordinates,
  cameraInsets,
  recenterRequest,
  onDisplayedFrame,
  onFailedImage,
}: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const debugMarkerRef = useRef<Marker | null>(null);
  const initial = useRef({ radar, cameraInsets });
  const active = useRef<{
    slot: 0 | 1;
    key: string;
    frame: RadarTimelineFrame;
  } | null>(null);
  const sequence = useRef(0);
  const presentation = useRef({
    opacity,
    reducedMotion,
    onDisplayedFrame,
    onFailedImage,
  });
  const [mapReady, setMapReady] = useState(false);
  const [displayed, setDisplayed] = useState<RadarTimelineFrame | null>(null);
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);
  const [coverageError, setCoverageError] = useState(false);

  useEffect(() => {
    presentation.current = {
      opacity,
      reducedMotion,
      onDisplayedFrame,
      onFailedImage,
    };
  }, [opacity, reducedMotion, onDisplayedFrame, onFailedImage]);
  // App da al mapa key=radar.id. Renovar el catálogo no recrea el mapa ni su cámara.
  useEffect(() => {
    if (!containerRef.current) return;
    const { radar: firstRadar, cameraInsets: firstInsets } = initial.current;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: import.meta.env.VITE_MAP_STYLE_URL?.trim() || DEFAULT_STYLE_URL,
      center: radarCameraCenter(firstRadar),
      zoom: initialRadarZoom(firstRadar, containerRef.current.clientWidth),
      minZoom: 4,
      maxZoom: 12,
      bearing: 0,
      pitch: 0,
      attributionControl: false,
    });
    map.setPadding(radarCameraPadding(firstRadar, firstInsets));
    mapRef.current = map;
    map.addControl(
      new NavigationControl({ showCompass: false, visualizePitch: false }),
      'top-right',
    );
    map.addControl(
      new AttributionControl({
        compact: false,
        customAttribution:
          '<a href="https://www.aemet.es/es/eltiempo/observacion/radar/ayuda" target="_blank" rel="noreferrer">Datos radar © AEMET</a>',
      }),
      'bottom-right',
    );
    map.once('style.load', () => {
      improvePlaceLabels(map);
      map.addSource(DEBUG_SOURCE_ID, debugSource(firstRadar));
      map.addLayer({
        id: DEBUG_LAYER_ID,
        type: 'line',
        source: DEBUG_SOURCE_ID,
        layout: { visibility: 'none' },
        paint: {
          'line-color': '#ff6a3d',
          'line-width': 2,
          'line-dasharray': [2, 2],
        },
      });
      if (firstRadar.kind === 'regional') {
        debugMarkerRef.current = createDebugMarker(map, firstRadar, false);
        map.addSource(NOMINAL_ID, {
          type: 'geojson',
          data: {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [
                [
                  [-179.99, -85],
                  [179.99, -85],
                  [179.99, 85],
                  [-179.99, 85],
                  [-179.99, -85],
                ],
                firstRadar.coverageRing,
              ],
            },
          },
        });
        map.addLayer(
          {
            id: NOMINAL_ID,
            type: 'fill',
            source: NOMINAL_ID,
            layout: { visibility: 'none' },
            paint: { 'fill-color': '#535b69', 'fill-opacity': 0.22 },
          },
          firstLabelLayer(map.getStyle()),
        );
      }
      setMapReady(true);
    });
    return () => {
      sequence.current += 1;
      mapRef.current = null;
      debugMarkerRef.current = null;
      map.remove();
    };
  }, []);

  useEffect(() => {
    mapRef.current?.setPadding(radarCameraPadding(radar, cameraInsets));
  }, [radar, cameraInsets]);
  const lastRecenter = useRef(recenterRequest);
  useEffect(() => {
    if (lastRecenter.current === recenterRequest) return;
    lastRecenter.current = recenterRequest;
    mapRef.current?.jumpTo({
      center: radarCameraCenter(radar),
      zoom: initialRadarZoom(radar, containerRef.current?.clientWidth ?? 0),
      padding: radarCameraPadding(radar, cameraInsets),
      bearing: 0,
      pitch: 0,
    });
  }, [recenterRequest, radar, cameraInsets]);

  useEffect(() => {
    const attempt = ++sequence.current; // También invalida B al volver a A o a un hueco.
    const map = mapRef.current;
    if (!mapReady || !map) return;
    setFailedImageUrl(null);
    const announce = (frame: RadarTimelineFrame | null) => {
      if (sequence.current !== attempt || mapRef.current !== map) return;
      setDisplayed(frame);
      presentation.current.onDisplayedFrame(frame);
      if (frame) recordRadarRendered(frame.imageUrl);
    };
    if (!selectedFrame) {
      for (const id of RADAR_IDS)
        if (map.getLayer(id)) map.setPaintProperty(id, 'raster-opacity', 0);
      active.current = null;
      const cleared = () => announce(null);
      map.once('render', cleared);
      map.triggerRepaint();
      return () => {
        map.off('render', cleared);
      };
    }
    const key = JSON.stringify([
      selectedFrame.imageUrl,
      selectedFrame.imageCoordinates,
    ]);
    if (active.current?.key === key) {
      active.current.frame = selectedFrame;
      const unchanged = () => announce(selectedFrame);
      map.once('render', unchanged);
      map.triggerRepaint();
      return () => {
        map.off('render', unchanged);
      };
    }
    const controller = new AbortController();
    const incoming = active.current?.slot === 0 ? 1 : 0;
    const id = RADAR_IDS[incoming];
    let committed = false;
    const acknowledge = () => {
      if (sequence.current !== attempt || mapRef.current !== map) return;
      setDisplayed(selectedFrame);
      presentation.current.onDisplayedFrame(selectedFrame);
      recordRadarRendered(selectedFrame.imageUrl);
    };
    void prepareMapImage(
      map,
      id,
      selectedFrame.imageUrl,
      selectedFrame.imageCoordinates,
      controller.signal,
    )
      .then(() => {
        if (
          sequence.current !== attempt ||
          controller.signal.aborted ||
          mapRef.current !== map
        )
          return;
        const { opacity: alpha, reducedMotion: reduced } = presentation.current;
        for (const layer of RADAR_IDS)
          if (map.getLayer(layer)) {
            map.setPaintProperty(layer, 'raster-opacity-transition', {
              duration: reduced ? 0 : 180,
              delay: 0,
            });
            map.setPaintProperty(
              layer,
              'raster-opacity',
              layer === id ? alpha : 0,
            );
          }
        active.current = { slot: incoming, key, frame: selectedFrame };
        committed = true;
        map.once('render', acknowledge);
        map.triggerRepaint();
      })
      .catch((error: unknown) => {
        if (
          !controller.signal.aborted &&
          sequence.current === attempt &&
          mapRef.current === map
        ) {
          setFailedImageUrl(selectedFrame.imageUrl);
          presentation.current.onFailedImage(selectedFrame.imageUrl);
          removeMapImage(map, id);
        }
        void error;
      });
    return () => {
      controller.abort();
      map.off('render', acknowledge);
      if (!committed && mapRef.current === map) removeMapImage(map, id);
    };
  }, [mapReady, selectedFrame]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !active.current) return;
    for (const [slot, id] of RADAR_IDS.entries())
      if (map.getLayer(id))
        map.setPaintProperty(
          id,
          'raster-opacity',
          slot === active.current.slot ? opacity : 0,
        );
  }, [mapReady, opacity]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    map.setLayoutProperty(
      DEBUG_LAYER_ID,
      'visibility',
      showDebug ? 'visible' : 'none',
    );
    if (debugMarkerRef.current)
      debugMarkerRef.current.getElement().hidden = !showDebug;
  }, [mapReady, showDebug]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    setCoverageError(false);
    if (map.getLayer(NOMINAL_ID))
      map.setLayoutProperty(
        NOMINAL_ID,
        'visibility',
        showNoCoverage ? 'visible' : 'none',
      );
    removeMapImage(map, NO_COVERAGE_ID);
    if (!showNoCoverage || !displayed?.noCoverageUrl) return;
    const controller = new AbortController();
    void prepareMapImage(
      map,
      NO_COVERAGE_ID,
      displayed.noCoverageUrl,
      displayed.imageCoordinates,
      controller.signal,
    )
      .then(() => {
        if (controller.signal.aborted || mapRef.current !== map) return;
        const radarLayer = RADAR_IDS.find((id) => map.getLayer(id));
        if (radarLayer) map.moveLayer(NO_COVERAGE_ID, radarLayer);
        map.setPaintProperty(NO_COVERAGE_ID, 'raster-opacity', 0.3);
      })
      .catch(() => {
        if (!controller.signal.aborted) setCoverageError(true);
      });
    return () => {
      controller.abort();
      if (mapRef.current === map) removeMapImage(map, NO_COVERAGE_ID);
    };
  }, [mapReady, showNoCoverage, displayed]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !userCoordinates) return;
    const element = document.createElement('div');
    element.className = 'user-location-marker';
    element.setAttribute('aria-label', 'Tu ubicación aproximada');
    element.title = 'Tu ubicación aproximada';
    const marker = new Marker({ element })
      .setLngLat(userCoordinates)
      .addTo(map);
    return () => {
      marker.remove();
    };
  }, [mapReady, userCoordinates]);

  return (
    <div
      className="map-stage"
      data-map-ready={mapReady ? 'true' : 'false'}
      data-frame-ready={displayed?.imageUrl ?? ''}
      data-top-inset={cameraInsets.top}
      data-bottom-inset={cameraInsets.bottom}
    >
      <div
        ref={containerRef}
        className="map-canvas"
        role="region"
        aria-label={`Mapa del radar de ${radar.label}`}
      />
      {!mapReady && (
        <p className="map-loading" role="status">
          Cargando cartografía…
        </p>
      )}
      {selectedFrame && failedImageUrl === selectedFrame.imageUrl && (
        <p className="map-error" role="alert">
          No se pudo cargar este fotograma.{' '}
          {displayed
            ? 'Se conserva la imagen indicada en la línea de tiempo.'
            : 'El historial sigue disponible.'}
        </p>
      )}
      {showNoCoverage && (
        <p className="coverage-caption">
          {radar.kind === 'regional'
            ? `Gris: fuera del alcance nominal de ${radar.rangeKilometres} km. La cobertura real puede ser menor.`
            : coverageError
              ? 'No se pudo cargar la capa sin cobertura.'
              : displayed?.noCoverageUrl
                ? 'Gris: sin cobertura operativa según AEMET.'
                : 'Sin capa de cobertura para esta imagen.'}
        </p>
      )}
    </div>
  );
}

function createDebugMarker(
  map: MapLibreMap,
  radar: RegionalRadarIndexEntry,
  visible: boolean,
) {
  const element = document.createElement('div');
  element.className = 'debug-marker debug-marker--radar';
  element.setAttribute('aria-label', `Radar ${radar.siteName}`);
  element.title = `Radar ${radar.siteName}`;
  element.hidden = !visible;
  return new Marker({ element }).setLngLat(radar.coordinates).addTo(map);
}

function debugSource(radar: RadarIndexEntry): GeoJSONSourceSpecification {
  return {
    type: 'geojson',
    data: {
      type: 'Feature',
      properties: {
        kind: 'coverage',
        label:
          radar.kind === 'national'
            ? radar.coverageLabel
            : `Cobertura nominal ${radar.rangeKilometres} km`,
      },
      geometry: {
        type: 'LineString',
        coordinates: radar.coverageRing,
      },
    },
  };
}
