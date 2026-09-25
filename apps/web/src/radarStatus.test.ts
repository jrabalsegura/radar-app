import { describe, expect, it } from 'vitest';
import { radarStatus } from './radarStatus';
import type { RadarIndexEntry } from './radarIndex';
import type { RadarHealth } from './radarHealth';
const time = '2026-09-06T12:00:00Z';
const radar = {
  id: 'national',
  available: true,
  latestFrameTime: time,
  cadenceMinutes: 10,
} as RadarIndexEntry;
const health: RadarHealth = {
  schemaVersion: 1,
  generatedAt: time,
  status: 'ok',
  products: [
    {
      id: 'national',
      label: 'Nacional',
      status: 'current',
      lastFrameTime: time,
      lastPollAt: time,
      lastError: null,
    },
  ],
};
describe('frescura con reloj del cliente', () => {
  it('caduca un health congelado aunque siga llegando por HTTP 200', () => {
    expect(
      radarStatus(
        radar,
        null,
        health,
        Date.parse(time) + 5 * 60_000,
        false,
        false,
      ),
    ).toBe('current');
    expect(
      radarStatus(
        radar,
        null,
        health,
        Date.parse(time) + 41 * 60_000,
        false,
        false,
      ),
    ).toBe('delayed');
  });
  it('no marca como retrasada la latencia normal de AEMET', () => {
    const fresh = { ...health, generatedAt: '2026-09-06T12:30:00Z' };
    expect(
      radarStatus(
        radar,
        null,
        fresh,
        Date.parse(time) + 33 * 60_000,
        false,
        false,
      ),
    ).toBe('current');
  });
  it('sin health evalúa la edad y no confunde disponibilidad con actualidad', () => {
    expect(
      radarStatus(
        radar,
        null,
        null,
        Date.parse(time) + 86400_000,
        false,
        false,
      ),
    ).toBe('delayed');
    expect(
      radarStatus(
        { ...radar, latestFrameTime: null },
        null,
        null,
        Date.parse(time),
        false,
        false,
      ),
    ).toBe('no-data');
  });
  it('conserva el error y degrada las copias cacheadas', () => {
    expect(
      radarStatus(radar, null, health, Date.parse(time), true, false),
    ).toBe('delayed');
    expect(
      radarStatus(radar, null, health, Date.parse(time), false, true),
    ).toBe('error');
  });
});
