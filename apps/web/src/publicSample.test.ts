import { describe, expect, it } from 'vitest';

import publicIndex from '../public/radar/index.json';
import publicHealth from '../public/status/health.json';
import { isRadarHealth } from './radarHealth';
import { isRadarIndex } from './radarIndex';
import {
  buildTimelineSlots,
  isRadarManifest,
  type RadarManifest,
} from './radarManifest';

const manifestModules = import.meta.glob(
  [
    '../public/radar/national/manifest.json',
    '../public/radar/regional-*/manifest.json',
  ],
  {
    eager: true,
    import: 'default',
  },
);
const frameImages = import.meta.glob(
  [
    '../public/radar/regional-*/frames/*/overlay-3857.png',
    '../public/radar/regional-*/frames/*/overlay.png',
    '../public/radar/national/frames/*/overlay.png',
  ],
  {
    eager: true,
    import: 'default',
    query: '?url',
  },
);
const imageUrls = new Set(
  Object.keys(frameImages).map((path) => path.replace('../public', '')),
);

describe('muestra pública de la fase 7', () => {
  it('publica el catálogo completo y conserva los radares sin datos', () => {
    const indexPayload: unknown = publicIndex;
    const healthPayload: unknown = publicHealth;

    expect(isRadarIndex(indexPayload)).toBe(true);
    expect(isRadarHealth(healthPayload)).toBe(true);
    if (!isRadarIndex(indexPayload) || !isRadarHealth(healthPayload)) {
      return;
    }
    expect(indexPayload.radars).toHaveLength(16);
    expect(indexPayload.radars.filter((radar) => radar.available)).toHaveLength(
      15,
    );
    expect(
      indexPayload.radars
        .filter((radar) => !radar.available)
        .map((radar) => radar.id),
    ).toEqual(['regional-va']);
    expect(healthPayload.products).toHaveLength(16);
  });

  it('mantiene separado cada manifiesto y referencia únicamente PNG existentes', () => {
    expect(Object.keys(manifestModules)).toHaveLength(16);
    const manifests = Object.values(manifestModules).filter(
      (payload): payload is RadarManifest => isRadarManifest(payload),
    );
    expect(manifests).toHaveLength(16);

    for (const manifest of manifests) {
      const indexRadar = isRadarIndex(publicIndex)
        ? publicIndex.radars.find((radar) => radar.id === manifest.radar.id)
        : undefined;
      expect(indexRadar).toBeDefined();
      expect(manifest.window.hours).toBe(230 / 60);
      expect(manifest.window.minutes).toBe(230);
      expect(manifest.frames.length > 0).toBe(indexRadar?.available);
      expect(
        manifest.frames.every(
          (frame) =>
            frame.imageUrl.startsWith(`/radar/${manifest.radar.id}/frames/`) &&
            imageUrls.has(frame.imageUrl),
        ),
      ).toBe(true);
    }

    const byId = new Map(
      manifests.map((manifest) => [manifest.radar.id, manifest]),
    );
    expect(byId.get('national')?.radar.kind).toBe('national');
    expect(byId.get('national')?.frames).toHaveLength(24);
    expect(buildTimelineSlots(byId.get('national')!)).toHaveLength(24);
    expect(byId.get('regional-co')?.frames).toHaveLength(24);
    expect(byId.get('regional-ss')?.frames).toHaveLength(24);
    expect(byId.get('regional-mu')?.frames).toHaveLength(24);
    expect(byId.get('regional-ml')?.frames).toHaveLength(3);
    expect(byId.get('regional-ml')?.gaps[0]?.missingCount).toBe(21);
    expect(buildTimelineSlots(byId.get('regional-ml')!)).toHaveLength(24);
    expect(byId.get('regional-ca')?.frames).toHaveLength(1);
    expect(byId.get('regional-va')?.frames).toHaveLength(0);
  });
});
