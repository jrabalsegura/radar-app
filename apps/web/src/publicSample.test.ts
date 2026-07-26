import { describe, expect, it } from 'vitest';

import publicManifest from '../public/radar/regional-mu/manifest.json';
import { isRadarManifest } from './radarManifest';

const frameImages = import.meta.glob(
  '../public/radar/regional-mu/frames/*/overlay-3857.png',
  {
    eager: true,
    import: 'default',
    query: '?url',
  },
);
const imageUrls = new Set(
  Object.keys(frameImages).map((path) => path.replace('../public', '')),
);

describe('muestra pública de la fase 5', () => {
  it('contiene tres horas reales, huecos explícitos y un PNG por observación', () => {
    const payload: unknown = publicManifest;

    expect(isRadarManifest(payload)).toBe(true);
    if (!isRadarManifest(payload)) {
      return;
    }
    expect(payload.window.hours).toBe(3);
    expect(payload.frames).toHaveLength(18);
    expect(payload.gaps).toHaveLength(3);
    expect(frameImages).toBeDefined();
    expect(imageUrls.size).toBe(18);
    expect(payload.frames.every((frame) => imageUrls.has(frame.imageUrl))).toBe(
      true,
    );
  });
});
