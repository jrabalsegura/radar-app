import { afterEach, describe, expect, it, vi } from 'vitest';

import { preloadFrame, prioritizedFrameUrls } from './framePreloader';
import type { TimelineSlot } from './radarManifest';

describe('framePreloader', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('comparte una única carga para una URL ya solicitada', async () => {
    let assignments = 0;
    class FakeImage {
      decoding = '';
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      set src(_value: string) {
        assignments += 1;
        queueMicrotask(() => this.onload?.());
      }
    }
    vi.stubGlobal('Image', FakeImage);

    const first = preloadFrame('/radar/frame-cache-test.png');
    const second = preloadFrame('/radar/frame-cache-test.png');

    expect(second).toBe(first);
    await first;
    expect(assignments).toBe(1);
  });

  it('prioriza el último fotograma y después los cercanos al seleccionado', () => {
    const slots = [
      frameSlot('one', '/one.png', '2026-07-24T17:00:00Z'),
      frameSlot('two', '/two.png', '2026-07-24T17:10:00Z'),
      {
        kind: 'gap',
        id: 'gap',
        time: '2026-07-24T17:20:00Z',
        gap: {
          after: '2026-07-24T17:10:00Z',
          before: '2026-07-24T17:30:00Z',
          expectedCadenceMinutes: 10,
          missingCount: 1,
          expectedTimes: ['2026-07-24T17:20:00Z'],
          timeBasis: 'retrievedAt',
        },
      },
      frameSlot('three', '/three.png', '2026-07-24T17:30:00Z'),
    ] satisfies TimelineSlot[];

    expect(prioritizedFrameUrls(slots, 1)).toEqual([
      '/three.png',
      '/two.png',
      '/one.png',
    ]);
  });
});

function frameSlot(id: string, imageUrl: string, time: string): TimelineSlot {
  return {
    kind: 'frame',
    id,
    time,
    frame: {
      id,
      time,
      timeSource: 'retrievedAt',
      productTime: null,
      retrievedAt: time,
      lastRetrievedAt: time,
      sourceHash: `sha256:${id.padEnd(64, '0')}`,
      rawUrl: `/${id}.gif`,
      imageUrl,
      imageCoordinates: [
        [-4, 40],
        [1, 40],
        [1, 36],
        [-4, 36],
      ],
      status: 'available',
    },
  };
}
