import { describe, expect, it } from 'vitest';

import publicIndex from '../public/radar/index.json';
import publicHealth from '../public/status/health.json';
import { isRadarHealth } from './radarHealth';
import { isRadarIndex } from './radarIndex';
import { isRadarManifest, type RadarManifest } from './radarManifest';

const manifestModules = import.meta.glob(
  '../public/radar/regional-*/manifest.json',
  {
    eager: true,
    import: 'default',
  },
);
const frameImages = import.meta.glob(
  '../public/radar/regional-*/frames/*/overlay-3857.png',
  {
    eager: true,
    import: 'default',
    query: '?url',
  },
);
const imageUrls = new Set(
  Object.keys(frameImages).map((path) => path.replace('../public', '')),
);

describe('muestra pública de la fase 6', () => {
  it('publica el catálogo completo y conserva los radares sin datos', () => {
    const indexPayload: unknown = publicIndex;
    const healthPayload: unknown = publicHealth;

    expect(isRadarIndex(indexPayload)).toBe(true);
    expect(isRadarHealth(healthPayload)).toBe(true);
    if (!isRadarIndex(indexPayload) || !isRadarHealth(healthPayload)) {
      return;
    }
    expect(indexPayload.radars).toHaveLength(15);
    expect(indexPayload.radars.filter((radar) => radar.available)).toHaveLength(
      12,
    );
    expect(
      indexPayload.radars
        .filter((radar) => !radar.available)
        .map((radar) => radar.id),
    ).toEqual(['regional-co', 'regional-va', 'regional-ss']);
    expect(healthPayload.products).toHaveLength(15);
  });

  it('mantiene separado cada manifiesto y referencia únicamente PNG existentes', () => {
    expect(Object.keys(manifestModules)).toHaveLength(15);
    const manifests = Object.values(manifestModules).filter(
      (payload): payload is RadarManifest => isRadarManifest(payload),
    );
    expect(manifests).toHaveLength(15);

    for (const manifest of manifests) {
      const indexRadar = isRadarIndex(publicIndex)
        ? publicIndex.radars.find((radar) => radar.id === manifest.radar.id)
        : undefined;
      expect(indexRadar).toBeDefined();
      expect(manifest.window.hours).toBe(3);
      expect(manifest.frames.length > 0).toBe(indexRadar?.available);
      expect(
        manifest.frames.every(
          (frame) =>
            frame.imageUrl.startsWith(`/radar/${manifest.radar.id}/frames/`) &&
            imageUrls.has(frame.imageUrl),
        ),
      ).toBe(true);
    }
  });
});
