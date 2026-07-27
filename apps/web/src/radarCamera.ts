import type { RadarIndexEntry } from './radarIndex';

const REGIONAL_REFERENCE_VIEWPORT_WIDTH = 768;
const MINIMUM_ZOOM = 4;
const MAXIMUM_ZOOM = 12;

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
  bottomInset: number,
) {
  return {
    top: 0,
    right: 0,
    bottom: radar.kind === 'regional' ? Math.max(0, bottomInset) : 0,
    left: 0,
  };
}
