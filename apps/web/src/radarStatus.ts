import type { RadarHealth, RadarHealthStatus } from './radarHealth';
import type { RadarIndexEntry } from './radarIndex';
import type { RadarManifest } from './radarManifest';

// Igual que el worker: AEMET publica ~18 min tarde y el último dato normal llega a
// ~33 min de antigüedad. El refresco cada 5 min mantiene al cliente en ese margen.
const STALE_AFTER_CADENCES = 4;

export function radarStatus(
  radar: RadarIndexEntry,
  manifest: RadarManifest | null,
  health: RadarHealth | null,
  now: number,
  cached: boolean,
  failed: boolean,
): RadarHealthStatus {
  if (failed) return 'error';
  const product = health?.products.find((item) => item.id === radar.id);
  if (product?.status === 'error') return 'error';
  const lastFrame = manifest ? manifest.latestFrameTime : radar.latestFrameTime;
  if (!lastFrame) return 'no-data';
  const maximumAge = radar.cadenceMinutes * STALE_AFTER_CADENCES * 60_000;
  const age = now - Date.parse(lastFrame);
  const healthAge = health ? now - Date.parse(health.generatedAt) : 0;
  if (
    cached ||
    age > maximumAge ||
    age < -5 * 60_000 ||
    healthAge > maximumAge ||
    product?.status === 'delayed' ||
    product?.status === 'no-data'
  )
    return 'delayed';
  return 'current';
}
