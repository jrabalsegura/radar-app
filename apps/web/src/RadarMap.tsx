import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSourceSpecification,
} from 'maplibre-gl';
import mapLibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { useCallback, useEffect, useRef, useState } from 'react';
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
const DEBUG_SOURCE_ID = 'calibration-debug';
const DEBUG_LAYER_ID = 'coverage-debug';
const NO_COVERAGE_ID = 'no-coverage';
const NOMINAL_ID = 'outside-nominal-coverage';
interface RadarMapProps {
  radar: RadarIndexEntry;
  selectedFrame: RadarTimelineFrame | null;
  /** Fotogramas del historial: se precargan como capas ocultas para animar sin parpadeo. */
  frames: readonly RadarTimelineFrame[];
  opacity: number;
  showDebug: boolean;
  showNoCoverage: boolean;
  userCoordinates: LongitudeLatitude | null;
  cameraInsets: RadarCameraInsets;
  recenterRequest: number;
  onDisplayedFrame: (frame: RadarTimelineFrame | null) => void;
  onFailedImage: (url: string) => void;
}
export function RadarMap({
  radar,
  selectedFrame,
  frames,
  opacity,
  showDebug,
  showNoCoverage,
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
  // Una capa oculta por fotograma cargado: cambiar de instante solo cambia opacidades.
  const layers = useRef(new Map<string, FrameLayer>());
  const nextLayerId = useRef(0);
  const active = useRef<string | null>(null);
  const selectedKey = useRef<string | null>(null);
  const sequence = useRef(0);
  const presentation = useRef({
    opacity,
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
      onDisplayedFrame,
      onFailedImage,
    };
  }, [opacity, onDisplayedFrame, onFailedImage]);
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
    // Los móviles liberan el contexto WebGL de una app en segundo plano. MapLibre
    // restaura el estilo, pero sus fuentes imagen vuelven a cargar a la vez y
    // sin avisar: los fotogramas «cargados» se verían vacíos. Se descartan y se
    // recargan como al abrir la app, conservando cada uno hasta que está listo.
    map.on('webglcontextlost', () => {
      sequence.current += 1;
      setMapReady(false);
    });
    map.on('webglcontextrestored', () => {
      map.once('style.load', () => {
        for (const { id } of layers.current.values()) removeMapImage(map, id);
        layers.current.clear();
        active.current = null;
        removeMapImage(map, NO_COVERAGE_ID);
        setMapReady(true);
      });
    });
    const cachedLayers = layers.current;
    return () => {
      sequence.current += 1;
      cachedLayers.clear();
      active.current = null;
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

  // Devuelve la capa del fotograma, creándola oculta si aún no existe.
  const ensureLayer = useCallback(
    (map: MapLibreMap, frame: RadarTimelineFrame): FrameLayer => {
      const key = frameKey(frame);
      const existing = layers.current.get(key);
      if (existing) return existing;
      const layer: FrameLayer = {
        id: `radar-frame-${nextLayerId.current++}`,
        loaded: false,
        ready: Promise.resolve(),
      };
      layer.ready = prepareMapImage(
        map,
        layer.id,
        frame.imageUrl,
        frame.imageCoordinates,
      ).then(
        () => {
          layer.loaded = true;
          // Cambio instantáneo: un fundido cruzado atenúa ambas capas a la vez.
          map.setPaintProperty(layer.id, 'raster-opacity-transition', {
            duration: 0,
            delay: 0,
          });
        },
        (error: unknown) => {
          if (layers.current.get(key) === layer) layers.current.delete(key);
          if (mapRef.current === map) removeMapImage(map, layer.id);
          throw error;
        },
      );
      layers.current.set(key, layer);
      return layer;
    },
    [],
  );

  useEffect(() => {
    const attempt = ++sequence.current; // Invalida cargas pendientes de selecciones previas.
    selectedKey.current = selectedFrame ? frameKey(selectedFrame) : null;
    const map = mapRef.current;
    if (!mapReady || !map) return;
    setFailedImageUrl(null);
    let rendered: (() => void) | null = null;
    const display = (
      layerId: string | null,
      frame: RadarTimelineFrame | null,
    ) => {
      active.current = layerId;
      showLayer(map, layers.current, layerId, presentation.current.opacity);
      rendered = () => {
        if (sequence.current !== attempt || mapRef.current !== map) return;
        setDisplayed(frame);
        presentation.current.onDisplayedFrame(frame);
        if (frame) recordRadarRendered(frame.imageUrl);
      };
      map.once('render', rendered);
      map.triggerRepaint();
    };
    if (!selectedFrame) {
      display(null, null);
    } else {
      const layer = ensureLayer(map, selectedFrame);
      if (layer.loaded) {
        display(layer.id, selectedFrame);
      } else {
        // Mientras carga se conserva visible el fotograma anterior.
        layer.ready.then(
          () => {
            if (sequence.current === attempt && mapRef.current === map)
              display(layer.id, selectedFrame);
          },
          () => {
            if (sequence.current !== attempt || mapRef.current !== map) return;
            setFailedImageUrl(selectedFrame.imageUrl);
            presentation.current.onFailedImage(selectedFrame.imageUrl);
          },
        );
      }
    }
    return () => {
      if (rendered) map.off('render', rendered);
    };
  }, [ensureLayer, mapReady, selectedFrame]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    const wanted = new Set(frames.map(frameKey));
    for (const [key, layer] of layers.current)
      if (
        !wanted.has(key) &&
        key !== selectedKey.current &&
        layer.id !== active.current
      ) {
        layers.current.delete(key);
        removeMapImage(map, layer.id);
      }
    let cancelled = false;
    void (async () => {
      // Del más reciente al más antiguo, uno a uno, para no competir con la selección.
      for (const frame of [...frames].reverse()) {
        if (cancelled || mapRef.current !== map) return;
        try {
          await ensureLayer(map, frame).ready;
        } catch {
          // El fallo se muestra solo si el usuario selecciona ese fotograma.
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ensureLayer, frames, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !active.current) return;
    showLayer(map, layers.current, active.current, opacity);
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
        if (active.current && map.getLayer(active.current))
          map.moveLayer(NO_COVERAGE_ID, active.current);
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

interface FrameLayer {
  id: string;
  loaded: boolean;
  ready: Promise<void>;
}

function frameKey(frame: RadarTimelineFrame): string {
  return JSON.stringify([frame.imageUrl, frame.imageCoordinates]);
}

function showLayer(
  map: MapLibreMap,
  layers: Map<string, FrameLayer>,
  visibleId: string | null,
  opacity: number,
): void {
  for (const { id } of layers.values())
    if (map.getLayer(id))
      map.setPaintProperty(
        id,
        'raster-opacity',
        id === visibleId ? opacity : 0,
      );
}
