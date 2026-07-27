import { afterEach, describe, expect, it, vi } from 'vitest';

import { cacheKey, loadResilientJson } from './resilientData';

interface Fixture {
  schemaVersion: 1;
  label: string;
}

const isFixture = (value: unknown): value is Fixture =>
  typeof value === 'object' &&
  value !== null &&
  'schemaVersion' in value &&
  value.schemaVersion === 1 &&
  'label' in value &&
  typeof value.label === 'string';

describe('loadResilientJson', () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it('guarda únicamente una respuesta de red válida', async () => {
    const fixture = { schemaVersion: 1, label: 'red' } as const;
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => fixture,
      }),
    );

    const result = await loadResilientJson(
      '/fixture.json',
      'fixture',
      isFixture,
    );

    expect(result).toMatchObject({ data: fixture, source: 'network' });
    expect(window.localStorage.getItem(cacheKey('fixture'))).toContain('"red"');
  });

  it('recupera la última copia válida cuando falla la red', async () => {
    window.localStorage.setItem(
      cacheKey('fixture'),
      JSON.stringify({
        schemaVersion: 1,
        savedAt: '2026-07-27T10:00:00Z',
        value: { schemaVersion: 1, label: 'guardada' },
      }),
    );
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));

    await expect(
      loadResilientJson('/fixture.json', 'fixture', isFixture),
    ).resolves.toEqual({
      data: { schemaVersion: 1, label: 'guardada' },
      source: 'cache',
      savedAt: '2026-07-27T10:00:00Z',
    });
  });

  it('descarta una copia manipulada o incompatible', async () => {
    window.localStorage.setItem(
      cacheKey('fixture'),
      JSON.stringify({
        schemaVersion: 1,
        savedAt: '2026-07-27T10:00:00Z',
        value: { schemaVersion: 2, label: 'antigua' },
      }),
    );
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));

    await expect(
      loadResilientJson('/fixture.json', 'fixture', isFixture),
    ).rejects.toThrow('offline');
    expect(window.localStorage.getItem(cacheKey('fixture'))).toBeNull();
  });
});
