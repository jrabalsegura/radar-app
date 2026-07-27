import { describe, expect, it } from 'vitest';

import type { RadarIndexEntry } from './radarIndex';
import { closestRegionalRadar, haversineKilometres } from './radarLocation';

const regional = (id: string, coordinates: [number, number]) =>
  ({
    id,
    label: id,
    kind: 'regional',
    cadenceMinutes: 10,
    manifestUrl: `/radar/${id}/manifest.json`,
    available: true,
    latestFrameTime: null,
    coordinates,
    mapZoom: 6,
    coverageRing: [coordinates, coordinates, coordinates, coordinates],
    validation: { status: 'verified', sampleVerified: true },
    apiCode: id,
    siteCode: id,
    siteName: id,
    rangeKilometres: 240,
  }) satisfies RadarIndexEntry;

describe('radarLocation', () => {
  it('elige el emplazamiento regional geográficamente más cercano', () => {
    const radars = [
      regional('regional-norte', [-3.7, 43.4]),
      regional('regional-sur', [-2.9, 36.8]),
    ];

    expect(closestRegionalRadar(radars, [-3, 37])?.id).toBe('regional-sur');
  });

  it('calcula distancias de gran círculo en kilómetros', () => {
    expect(
      haversineKilometres([-3.7038, 40.4168], [2.1734, 41.3851]),
    ).toBeCloseTo(505, -1);
  });
});
