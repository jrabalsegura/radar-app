import type { RadarIndexEntry } from './radarIndex';

const REGIONAL_REFERENCE_VIEWPORT_WIDTH = 768;
const MINIMUM_ZOOM = 4;
const MAXIMUM_ZOOM = 12;

export interface RadarCameraInsets {
  top: number;
  bottom: number;
}

export function radarCameraCenter(radar: RadarIndexEntry): [number, number] {
  return radar.kind === 'regional' && radar.mapCenter
    ? radar.mapCenter
    : radar.coordinates;
}

export function initialRadarZoom(
  radar: RadarIndexEntry,
  viewportWidth: number,
) {
  if (radar.kind === 'national' || viewportWidth <= 0) {
    return radar.mapZoom;
  }
  const responsiveOffset = Math.log2(
    viewportWidth / REGIONAL_REFERENCE_VIEWPORT_WIDTH,
  );
  return Math.min(
    MAXIMUM_ZOOM,
    Math.max(MINIMUM_ZOOM, radar.mapZoom + responsiveOffset),
  );
}

export function radarCameraPadding(
  radar: RadarIndexEntry,
  insets: RadarCameraInsets,
) {
  return {
    top: radar.kind === 'regional' ? Math.max(0, insets.top) : 0,
    right: 0,
    bottom: radar.kind === 'regional' ? Math.max(0, insets.bottom) : 0,
    left: 0,
  };
}
