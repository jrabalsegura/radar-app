import {
  AttributionControl,
  ImageSource,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type GeoJSONSourceSpecification,
} from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import 'maplibre-gl/dist/maplibre-gl.css';

import { preloadFrame } from './framePreloader';
import type { RadarFrameReport } from './radarFrame';
import type { RadarTimelineFrame } from './radarManifest';

const DEFAULT_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
const RADAR_SOURCE_IDS = [
  'regional-mu-frame-a',
  'regional-mu-frame-b',
] as const;
const RADAR_LAYER_IDS = ['regional-mu-frame-a', 'regional-mu-frame-b'] as const;
const DEBUG_SOURCE_ID = 'calibration-debug';
const DEBUG_LAYER_ID = 'coverage-debug';
const CROSSFADE_MILLISECONDS = 180;

interface RadarMapProps {
  calibration: RadarFrameReport;
  selectedFrame: RadarTimelineFrame | null;
  opacity: number;
  showDebug: boolean;
  reducedMotion: boolean;
}

export function RadarMap({
  calibration,
  selectedFrame,
  opacity,
  showDebug,
  reducedMotion,
}: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const debugMarkersRef = useRef<Marker[]>([]);
  const activeLayerRef = useRef<0 | 1>(0);
  const activeUrlRef = useRef(selectedFrame?.imageUrl ?? null);
  const initialUrlRef = useRef(
    selectedFrame?.imageUrl ?? '/radar/regional-mu/overlay-3857.png',
  );
  const initialFramePresentRef = useRef(selectedFrame !== null);
  const transitionSequenceRef = useRef(0);
  const initialOpacityRef = useRef(opacity);
  const initialDebugRef = useRef(showDebug);
  const [mapReady, setMapReady] = useState(false);
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const configuredStyle = import.meta.env.VITE_MAP_STYLE_URL?.trim();
    const map = new MapLibreMap({
      container: containerRef.current,
      style: configuredStyle || DEFAULT_STYLE_URL,
      center: calibration.radar.coordinates,
      zoom: 6.1,
      minZoom: 4.5,
      maxZoom: 12,
      bearing: 0,
      pitch: 0,
      attributionControl: false,
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
      for (const sourceId of RADAR_SOURCE_IDS) {
        map.addSource(sourceId, {
          type: 'image',
          url: initialUrlRef.current,
          coordinates: calibration.output.maplibreCoordinates,
        });
      }
      for (const [index, layerId] of RADAR_LAYER_IDS.entries()) {
        map.addLayer({
          id: layerId,
          type: 'raster',
          source: RADAR_SOURCE_IDS[index]!,
          paint: {
            'raster-opacity':
              initialFramePresentRef.current && index === 0
                ? initialOpacityRef.current
                : 0,
            'raster-fade-duration': 0,
            'raster-resampling': 'nearest',
          },
        });
      }

      map.addSource(DEBUG_SOURCE_ID, debugSource(calibration));
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
      debugMarkersRef.current = createDebugMarkers(
        map,
        calibration,
        initialDebugRef.current,
      );
      setMapReady(true);
    });

    return () => {
      transitionSequenceRef.current += 1;
      setMapReady(false);
      debugMarkersRef.current = [];
      mapRef.current = null;
      map.remove();
    };
  }, [calibration]);

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
    if (activeUrlRef.current === selectedFrame.imageUrl) {
      const active = activeLayerRef.current;
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
          coordinates: calibration.output.maplibreCoordinates,
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
  }, [calibration, mapReady, opacity, reducedMotion, selectedFrame]);

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
    for (const marker of debugMarkersRef.current) {
      marker.getElement().hidden = !showDebug;
    }
  }, [mapReady, showDebug]);

  return (
    <div className="map-stage">
      <div
        ref={containerRef}
        className="map-canvas"
        aria-label="Mapa animado del radar de Murcia"
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

function createDebugMarkers(
  map: MapLibreMap,
  frame: RadarFrameReport,
  visible: boolean,
) {
  const points = [
    {
      coordinates: frame.radar.coordinates,
      label: 'Radar Murcia–Fortuna',
      kind: 'radar',
    },
    ...frame.calibration.controlPoints.map((point) => ({
      coordinates: point.coordinates,
      label: `${point.label} · ${point.errorKilometres.toFixed(2)} km`,
      kind: 'control',
    })),
  ];
  return points.map((point) => {
    const element = document.createElement('div');
    element.className = `debug-marker debug-marker--${point.kind}`;
    element.setAttribute('aria-label', point.label);
    element.title = point.label;
    element.hidden = !visible;
    return new Marker({ element }).setLngLat(point.coordinates).addTo(map);
  });
}

function debugSource(frame: RadarFrameReport): GeoJSONSourceSpecification {
  return {
    type: 'geojson',
    data: {
      type: 'Feature',
      properties: {
        kind: 'coverage',
        label: `Cobertura nominal ${frame.radar.rangeKilometres} km`,
      },
      geometry: {
        type: 'LineString',
        coordinates: frame.debug.coverageRing,
      },
    },
  };
}
