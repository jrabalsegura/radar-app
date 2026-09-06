import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RadarMap } from './RadarMap';
import type { RadarTimelineFrame } from './radarManifest';

const { maps, MockMap } = vi.hoisted(() => {
  type Event = { sourceId?: string; sourceDataType?: string; error?: Error };
  type Handler = (event: Event) => void;
  const maps: FakeMap[] = [];
  class FakeMap {
    events = new Map<string, Set<Handler>>();
    layers = new Set<string>();
    sources = new Set<string>();
    constructor() {
      maps.push(this);
    }
    on(name: string, handler: Handler) {
      const handlers = this.events.get(name) ?? new Set();
      handlers.add(handler);
      this.events.set(name, handlers);
      return this;
    }
    off(name: string, handler: Handler) {
      this.events.get(name)?.delete(handler);
      return this;
    }
    once(name: string, handler: Handler) {
      const once: Handler = (event) => {
        this.off(name, once);
        handler(event);
      };
      return this.on(name, once);
    }
    fire(name: string, event: Event = {}) {
      for (const handler of [...(this.events.get(name) ?? [])]) handler(event);
    }
    getStyle() {
      return {
        version: 8,
        sources: {},
        layers: [{ id: 'place-label', type: 'symbol' }],
      };
    }
    addSource = vi.fn((id: string) => {
      this.sources.add(id);
    });
    addLayer = vi.fn((layer: { id: string }) => {
      this.layers.add(layer.id);
    });
    getSource(id: string) {
      return this.sources.has(id);
    }
    getLayer(id: string) {
      return this.layers.has(id);
    }
    removeLayer(id: string) {
      this.layers.delete(id);
    }
    removeSource(id: string) {
      this.sources.delete(id);
    }
    addControl = vi.fn();
    setPadding = vi.fn();
    jumpTo = vi.fn();
    remove = vi.fn();
    setPaintProperty = vi.fn();
    setLayoutProperty = vi.fn();
    moveLayer = vi.fn();
    triggerRepaint = vi.fn();
  }
  return { maps, MockMap: FakeMap };
});
vi.mock('maplibre-gl', () => ({
  Map: MockMap,
  setWorkerUrl: vi.fn(),
  NavigationControl: class {},
  AttributionControl: class {},
  Marker: class {
    element = document.createElement('div');
    setLngLat() {
      return this;
    }
    addTo() {
      return this;
    }
    getElement() {
      return this.element;
    }
    remove() {}
  },
}));
const coordinates: RadarTimelineFrame['imageCoordinates'] = [
  [-5, 42],
  [2, 42],
  [2, 36],
  [-5, 36],
];
function frame(id: string): RadarTimelineFrame {
  return {
    id,
    time: '2026-09-06T12:00:00Z',
    timeSource: 'productTime',
    productTime: '2026-09-06T12:00:00Z',
    retrievedAt: '2026-09-06T12:01:00Z',
    lastRetrievedAt: '2026-09-06T12:01:00Z',
    sourceHash: `sha256:${'a'.repeat(64)}`,
    rawUrl: `/raw/${id}.png`,
    imageUrl: `/radar/regional-mu/${id}.png`,
    imageCoordinates: coordinates,
    status: 'available',
  };
}
function props(): Parameters<typeof RadarMap>[0] {
  return {
    radar: {
      id: 'regional-mu',
      label: 'Murcia',
      kind: 'regional',
      cadenceMinutes: 10,
      manifestUrl: '/radar/regional-mu/manifest.json',
      available: true,
      latestFrameTime: '2026-09-06T12:00:00Z',
      apiCode: 'mu',
      siteCode: 'FTN',
      siteName: 'Murcia',
      coordinates: [-1.18, 38.26],
      rangeKilometres: 240,
      mapZoom: 6.1,
      coverageRing: [...coordinates, coordinates[0]],
      validation: { status: 'control-points', sampleVerified: true },
    },
    selectedFrame: frame('A'),
    opacity: 0.7,
    showDebug: false,
    showNoCoverage: false,
    reducedMotion: true,
    userCoordinates: null,
    cameraInsets: { top: 0, bottom: 160 },
    recenterRequest: 0,
    onDisplayedFrame: vi.fn(),
    onFailedImage: vi.fn(),
  };
}
async function load(slot: string) {
  await act(async () => {
    maps[0]!.fire('sourcedata', { sourceId: slot, sourceDataType: 'metadata' });
  });
  act(() => {
    maps[0]!.fire('render');
  });
}
afterEach(() => {
  cleanup();
  maps.splice(0);
});
describe('RadarMap: fuentes reales y cámara', () => {
  it('espera al render real y cancela B al volver a A', async () => {
    const input = props();
    const view = render(<RadarMap {...input} />);
    act(() => {
      maps[0]!.fire('style.load');
    });
    expect(input.onDisplayedFrame).not.toHaveBeenCalled();
    await load('regional-frame-a');
    expect(input.onDisplayedFrame).toHaveBeenLastCalledWith(
      input.selectedFrame,
    );
    view.rerender(<RadarMap {...input} selectedFrame={frame('B')} />);
    view.rerender(<RadarMap {...input} />);
    await load('regional-frame-b');
    expect(input.onDisplayedFrame).toHaveBeenLastCalledWith(
      input.selectedFrame,
    );
    expect(maps[0]!.layers.has('regional-frame-b')).toBe(false);
    expect(maps[0]!.addLayer).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'regional-frame-a' }),
      'place-label',
    );
  });
  it('cancela una descarga al seleccionar un hueco sin imagen anterior', async () => {
    const input = props();
    const view = render(<RadarMap {...input} />);
    act(() => {
      maps[0]!.fire('style.load');
    });
    await load('regional-frame-a');
    view.rerender(<RadarMap {...input} selectedFrame={frame('B')} />);
    view.rerender(<RadarMap {...input} selectedFrame={null} />);
    await load('regional-frame-b');
    expect(input.onDisplayedFrame).toHaveBeenLastCalledWith(null);
    expect(document.querySelector('.map-stage')).toHaveAttribute(
      'data-frame-ready',
      '',
    );
  });
  it('renovar el catálogo o cambiar el panel conserva la cámara; centrar es explícito', () => {
    const input = props();
    const view = render(<RadarMap {...input} />);
    view.rerender(
      <RadarMap
        {...input}
        radar={{ ...input.radar }}
        cameraInsets={{ top: 0, bottom: 210 }}
      />,
    );
    expect(maps).toHaveLength(1);
    expect(maps[0]!.remove).not.toHaveBeenCalled();
    expect(maps[0]!.jumpTo).not.toHaveBeenCalled();
    view.rerender(<RadarMap {...input} recenterRequest={1} />);
    expect(maps[0]!.jumpTo).toHaveBeenCalledOnce();
  });
  it('un fallo de la primera imagen no se anuncia como imagen dibujada', async () => {
    const input = props();
    render(<RadarMap {...input} />);
    act(() => {
      maps[0]!.fire('style.load');
    });
    await act(async () => {
      maps[0]!.fire('error', {
        sourceId: 'regional-frame-a',
        error: new Error('404'),
      });
    });
    expect(input.onDisplayedFrame).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'No se pudo cargar este fotograma',
    );
  });
});
