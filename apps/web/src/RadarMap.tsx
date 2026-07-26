import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type GeoJSONSourceSpecification,
} from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';

import 'maplibre-gl/dist/maplibre-gl.css';

import type { RadarFrameReport } from './radarFrame';

const DEFAULT_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
const RADAR_SOURCE_ID = 'regional-mu-frame';
const RADAR_LAYER_ID = 'regional-mu-frame';
const DEBUG_SOURCE_ID = 'calibration-debug';
const DEBUG_LAYER_ID = 'coverage-debug';

interface RadarMapProps {
  frame: RadarFrameReport;
  opacity: number;
  showDebug: boolean;
}

export function RadarMap({ frame, opacity, showDebug }: RadarMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const debugMarkersRef = useRef<Marker[]>([]);
  const initialOpacityRef = useRef(opacity);
  const initialDebugRef = useRef(showDebug);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const configuredStyle = import.meta.env.VITE_MAP_STYLE_URL?.trim();
    const map = new MapLibreMap({
      container: containerRef.current,
      style: configuredStyle || DEFAULT_STYLE_URL,
      center: frame.radar.coordinates,
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
      map.addSource(RADAR_SOURCE_ID, {
        type: 'image',
        url: `/radar/regional-mu/${frame.output.file}`,
        coordinates: frame.output.maplibreCoordinates,
      });
      map.addLayer({
        id: RADAR_LAYER_ID,
        type: 'raster',
        source: RADAR_SOURCE_ID,
        paint: {
          'raster-opacity': initialOpacityRef.current,
          'raster-fade-duration': 0,
          'raster-resampling': 'nearest',
        },
      });

      map.addSource(DEBUG_SOURCE_ID, debugSource(frame));
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
        frame,
        initialDebugRef.current,
      );
      setMapReady(true);
    });

    return () => {
      setMapReady(false);
      debugMarkersRef.current = [];
      mapRef.current = null;
      map.remove();
    };
  }, [frame]);

  useEffect(() => {
    if (mapReady && mapRef.current?.getLayer(RADAR_LAYER_ID)) {
      mapRef.current.setPaintProperty(
        RADAR_LAYER_ID,
        'raster-opacity',
        opacity,
      );
    }
  }, [mapReady, opacity]);

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
        aria-label="Mapa georreferenciado del radar de Murcia"
      />
      {!mapReady && (
        <p className="map-loading" role="status">
          Cargando cartografía…
        </p>
      )}
    </div>
  );
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
    ...frame.debug.coverageRing.map((coordinates) => ({
      coordinates,
      label: 'Cobertura nominal de 240 km',
      kind: 'coverage',
    })),
  ];
  return points.map((point) => {
    const element = document.createElement('div');
    element.className = `debug-marker debug-marker--${point.kind}`;
    if (point.kind === 'coverage') {
      element.setAttribute('aria-hidden', 'true');
    } else {
      element.setAttribute('aria-label', point.label);
      element.title = point.label;
    }
    element.hidden = !visible;
    return new Marker({ element }).setLngLat(point.coordinates).addTo(map);
  });
}

function debugSource(frame: RadarFrameReport): GeoJSONSourceSpecification {
  return {
    type: 'geojson',
    data: {
      type: 'FeatureCollection',
      features: [
        {
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
        {
          type: 'Feature',
          properties: {
            kind: 'radar',
            label: 'Radar Murcia–Fortuna',
          },
          geometry: {
            type: 'Point',
            coordinates: frame.radar.coordinates,
          },
        },
        ...frame.calibration.controlPoints.map((point) => ({
          type: 'Feature' as const,
          properties: {
            kind: 'control',
            label: `${point.label} · ${point.errorKilometres.toFixed(2)} km`,
          },
          geometry: {
            type: 'Point' as const,
            coordinates: point.coordinates,
          },
        })),
      ],
    },
  };
}
