import { describe, expect, it } from 'vitest';

import {
  initialRadarZoom,
  radarCameraCenter,
  radarCameraPadding,
} from './radarCamera';
import type { RadarIndexEntry } from './radarIndex';

const regional = {
  kind: 'regional',
  mapZoom: 7.3,
  coordinates: [-1.19, 38.26],
  mapCenter: [-1.35, 37.84],
} as RadarIndexEntry;
const national = {
  kind: 'national',
  mapZoom: 4.4,
  coordinates: [-3.97, 39.25],
} as RadarIndexEntry;

describe('regional radar camera', () => {
  it('adapts the initial zoom to preserve a similar geographic radius', () => {
    expect(initialRadarZoom(regional, 768)).toBeCloseTo(7.3);
    expect(initialRadarZoom(regional, 1024)).toBeCloseTo(7.715, 3);
    expect(initialRadarZoom(regional, 575)).toBeCloseTo(6.882, 3);
  });

  it('keeps the national framing and reserves controls only for regionals', () => {
    expect(initialRadarZoom(national, 1024)).toBe(4.4);
    expect(radarCameraPadding(regional, { top: 150, bottom: 280 })).toEqual({
      top: 150,
      right: 0,
      bottom: 280,
      left: 0,
    });
    expect(radarCameraPadding(national, { top: 150, bottom: 280 })).toEqual({
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
    });
  });

  it('uses an explicit regional center without moving the radar location', () => {
    expect(radarCameraCenter(regional)).toEqual([-1.35, 37.84]);
    expect(radarCameraCenter(national)).toEqual([-3.97, 39.25]);
  });
});
