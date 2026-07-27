import { describe, expect, it } from 'vitest';

import { initialRadarZoom, radarCameraPadding } from './radarCamera';
import type { RadarIndexEntry } from './radarIndex';

const regional = {
  kind: 'regional',
  mapZoom: 7.3,
} as RadarIndexEntry;
const national = {
  kind: 'national',
  mapZoom: 4.4,
} as RadarIndexEntry;

describe('regional radar camera', () => {
  it('adapts the initial zoom to preserve a similar geographic radius', () => {
    expect(initialRadarZoom(regional, 768)).toBeCloseTo(7.3);
    expect(initialRadarZoom(regional, 1024)).toBeCloseTo(7.715, 3);
    expect(initialRadarZoom(regional, 575)).toBeCloseTo(6.882, 3);
  });

  it('keeps the national framing and reserves controls only for regionals', () => {
    expect(initialRadarZoom(national, 1024)).toBe(4.4);
    expect(radarCameraPadding(regional, 280).bottom).toBe(280);
    expect(radarCameraPadding(national, 280).bottom).toBe(0);
  });
});
