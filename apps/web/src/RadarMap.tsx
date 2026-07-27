import {
  AttributionControl,
  ImageSource,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  setWorkerUrl,
  type GeoJSONSourceSpecification,
} from 'maplibre-gl';
import mapLibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { useEffect, useRef, useState } from 'react';

import 'maplibre-gl/dist/maplibre-gl.css';

import { preloadFrame } from './framePreloader';
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
const RADAR_SOURCE_IDS = ['regional-frame-a', 'regional-frame-b'] as const;
const RADAR_LAYER_IDS = ['regional-frame-a', 'regional-frame-b'] as const;
const DEBUG_SOURCE_ID = 'calibration-debug';
const DEBUG_LAYER_ID = 'coverage-debug';
const CROSSFADE_MILLISECONDS = 180;

interface RadarMapProps {
  radar: RadarIndexEntry;
  selectedFrame: RadarTimelineFrame | null;
  opacity: number;
  showDebug: boolean;
  reducedMotion: boolean;
  userCoordinates: LongitudeLatitude | null;
  cameraInsets: RadarCameraInsets;
}

export function RadarMap({
  radar,
  selectedFrame,
  opacity,
  showDebug,
  reducedMotion,
  userCoordinates,
  cameraInsets,
}: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const debugMarkerRef = useRef<Marker | null>(null);
  const userMarkerRef = useRef<Marker | null>(null);
  const activeLayerRef = useRef<0 | 1>(0);
  const activeUrlRef = useRef<string | null>(null);
  const initialFrameRef = useRef(selectedFrame);
  const transitionSequenceRef = useRef(0);
  const initialOpacityRef = useRef(opacity);
  const initialDebugRef = useRef(showDebug);
  const initialCameraInsetsRef = useRef(cameraInsets);
  const [mapReady, setMapReady] = useState(false);
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    activeLayerRef.current = 0;
    activeUrlRef.current = initialFrameRef.current?.imageUrl ?? null;
    const configuredStyle = import.meta.env.VITE_MAP_STYLE_URL?.trim();
    const initialZoom = initialRadarZoom(
      radar,
      containerRef.current.clientWidth,
    );
    const initialCenter = radarCameraCenter(radar);
    const map = new MapLibreMap({
      container: containerRef.current,
      style: configuredStyle || DEFAULT_STYLE_URL,
      center: initialCenter,
      zoom: initialZoom,
      minZoom: 4,
      maxZoom: 12,
      bearing: 0,
      pitch: 0,
      attributionControl: false,
    });
    map.jumpTo({
      center: initialCenter,
      zoom: initialZoom,
      padding: radarCameraPadding(radar, initialCameraInsetsRef.current),
    });
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
      const initialFrame = initialFrameRef.current;
      if (initialFrame) {
        ensureRadarLayers(map, initialFrame, initialOpacityRef.current);
      }
      map.addSource(DEBUG_SOURCE_ID, debugSource(radar));
      map.addLayer({
        id: DEBUG_LAYER_ID,
        type: 'line',
        source: DEBUG_SOURCE_ID,
        layout: {
          visibility: initialDebugRef.current ? 'visible' : 'none',
        },
        paint: {
          'line-color': '#ff6a3d',
          'line-width': 2,
          'line-dasharray': [2, 2],
        },
      });
      debugMarkerRef.current =
        radar.kind === 'regional'
          ? createDebugMarker(map, radar, initialDebugRef.current)
          : null;
      setMapReady(true);
    });

    return () => {
      transitionSequenceRef.current += 1;
      setMapReady(false);
      debugMarkerRef.current = null;
      userMarkerRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, [radar]);

  useEffect(() => {
    mapRef.current?.jumpTo({
      center: radarCameraCenter(radar),
      zoom: initialRadarZoom(radar, containerRef.current?.clientWidth ?? 0),
      padding: radarCameraPadding(radar, cameraInsets),
    });
  }, [cameraInsets, radar]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) {
      return;
    }

    if (!selectedFrame) {
      activeUrlRef.current = null;
      setLayerOpacities(map, 0, 0, reducedMotion);
      return;
    }
    if (!map.getSource(RADAR_SOURCE_IDS[0])) {
      ensureRadarLayers(map, selectedFrame, opacity);
      activeLayerRef.current = 0;
      activeUrlRef.current = selectedFrame.imageUrl;
      return;
    }
    if (activeUrlRef.current === selectedFrame.imageUrl) {
      const active = activeLayerRef.current;
      updateActiveCoordinates(map, active, selectedFrame);
      setLayerOpacities(
        map,
        active === 0 ? opacity : 0,
        active === 1 ? opacity : 0,
        reducedMotion,
      );
      return;
    }

    const sequence = transitionSequenceRef.current + 1;
    transitionSequenceRef.current = sequence;
    void preloadFrame(selectedFrame.imageUrl)
      .then(() => {
        if (sequence !== transitionSequenceRef.current || !mapRef.current) {
          return;
        }
        const active = activeLayerRef.current;
        const incoming = active === 0 ? 1 : 0;
        const source = map.getSource(
          RADAR_SOURCE_IDS[incoming],
        ) as ImageSource | null;
        source?.updateImage({
          url: selectedFrame.imageUrl,
          coordinates: selectedFrame.imageCoordinates,
        });
        setLayerOpacities(
          map,
          incoming === 0 ? opacity : 0,
          incoming === 1 ? opacity : 0,
          reducedMotion,
        );
        activeLayerRef.current = incoming;
        activeUrlRef.current = selectedFrame.imageUrl;
        setFailedImageUrl(null);
      })
      .catch(() => {
        if (sequence === transitionSequenceRef.current) {
          setFailedImageUrl(selectedFrame.imageUrl);
        }
      });
  }, [mapReady, opacity, reducedMotion, selectedFrame]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !selectedFrame) {
      return;
    }
    const active = activeLayerRef.current;
    setLayerOpacities(
      map,
      active === 0 ? opacity : 0,
      active === 1 ? opacity : 0,
      reducedMotion,
    );
  }, [mapReady, opacity, reducedMotion, selectedFrame]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }
    if (mapRef.current.getLayer(DEBUG_LAYER_ID)) {
      mapRef.current.setLayoutProperty(
        DEBUG_LAYER_ID,
        'visibility',
        showDebug ? 'visible' : 'none',
      );
    }
    const marker = debugMarkerRef.current;
    if (marker) {
      marker.getElement().hidden = !showDebug;
    }
  }, [mapReady, showDebug]);

  useEffect(() => {
    const map = mapRef.current;
    userMarkerRef.current?.remove();
    userMarkerRef.current = null;
    if (!mapReady || !map || !userCoordinates) {
      return;
    }
    const element = document.createElement('div');
    element.className = 'user-location-marker';
    element.setAttribute('aria-label', 'Tu ubicación aproximada');
    element.title = 'Tu ubicación aproximada';
    userMarkerRef.current = new Marker({ element })
      .setLngLat(userCoordinates)
      .addTo(map);
    return () => {
      userMarkerRef.current?.remove();
      userMarkerRef.current = null;
    };
  }, [mapReady, userCoordinates]);

  return (
    <div
      className="map-stage"
      data-map-ready={mapReady ? 'true' : 'false'}
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
          No se pudo cargar este fotograma. El historial sigue disponible.
        </p>
      )}
    </div>
  );
}

function ensureRadarLayers(
  map: MapLibreMap,
  frame: RadarTimelineFrame,
  opacity: number,
) {
  for (const sourceId of RADAR_SOURCE_IDS) {
    map.addSource(sourceId, {
      type: 'image',
      url: frame.imageUrl,
      coordinates: frame.imageCoordinates,
    });
  }
  for (const [index, layerId] of RADAR_LAYER_IDS.entries()) {
    map.addLayer({
      id: layerId,
      type: 'raster',
      source: RADAR_SOURCE_IDS[index]!,
      paint: {
        'raster-opacity': index === 0 ? opacity : 0,
        'raster-fade-duration': 0,
        'raster-resampling': 'nearest',
      },
    });
  }
}

function updateActiveCoordinates(
  map: MapLibreMap,
  active: 0 | 1,
  frame: RadarTimelineFrame,
) {
  const source = map.getSource(RADAR_SOURCE_IDS[active]) as ImageSource | null;
  source?.updateImage({
    url: frame.imageUrl,
    coordinates: frame.imageCoordinates,
  });
}

function setLayerOpacities(
  map: MapLibreMap,
  first: number,
  second: number,
  reducedMotion: boolean,
) {
  const duration = reducedMotion ? 0 : CROSSFADE_MILLISECONDS;
  for (const [index, layerId] of RADAR_LAYER_IDS.entries()) {
    if (!map.getLayer(layerId)) {
      continue;
    }
    map.setPaintProperty(layerId, 'raster-opacity-transition', {
      duration,
      delay: 0,
    });
    map.setPaintProperty(
      layerId,
      'raster-opacity',
      index === 0 ? first : second,
    );
  }
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
