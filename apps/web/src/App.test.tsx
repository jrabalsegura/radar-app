import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { formatDataAge } from './dataFreshness';
import type { RadarIndexEntry } from './radarIndex';
import type { RadarTimelineFrame, TimelineSlot } from './radarManifest';
import { cacheKey } from './resilientData';

const { preloadSpy } = vi.hoisted(() => ({
  preloadSpy: vi.fn((slots: TimelineSlot[], selectedIndex: number) => {
    void slots;
    void selectedIndex;
    return vi.fn();
  }),
}));

vi.mock('./framePreloader', () => ({
  preloadInPriorityOrder: preloadSpy,
}));

vi.mock('./RadarMap', () => ({
  RadarMap: ({
    radar,
    selectedFrame,
    opacity,
    showDebug,
    reducedMotion,
  }: {
    radar: RadarIndexEntry;
    selectedFrame: RadarTimelineFrame | null;
    opacity: number;
    showDebug: boolean;
    reducedMotion: boolean;
  }) => (
    <div
      data-testid="radar-map"
      data-radar={radar.id}
      data-frame={selectedFrame?.id ?? 'none'}
      data-opacity={opacity}
      data-debug={showDebug}
      data-reduced-motion={reducedMotion}
    />
  ),
}));

const regionalCodes = [
  'am',
  'sa',
  'pm',
  'ba',
  'cc',
  'co',
  'ma',
  'ml',
  'mu',
  'vd',
  'ca',
  'se',
  'va',
  'ss',
  'za',
] as const;

const radarLabels: Record<(typeof regionalCodes)[number], string> = {
  am: 'Almería',
  sa: 'Asturias',
  pm: 'Illes Balears',
  ba: 'Barcelona',
  cc: 'Cáceres',
  co: 'A Coruña',
  ma: 'Madrid',
  ml: 'Málaga',
  mu: 'Murcia',
  vd: 'Palencia',
  ca: 'Las Palmas',
  se: 'Sevilla',
  va: 'Valencia',
  ss: 'Vizcaya',
  za: 'Zaragoza',
};

const regionalRadars = regionalCodes.map((code, index) => {
  const available = code !== 'co' && code !== 'va' && code !== 'ss';
  return {
    id: `regional-${code}`,
    label: radarLabels[code],
    kind: 'regional',
    cadenceMinutes: 10,
    manifestUrl: `/radar/regional-${code}/manifest.json`,
    available,
    latestFrameTime: available ? '2026-07-24T17:30:00Z' : null,
    apiCode: code,
    siteCode: code.toUpperCase(),
    siteName: `${radarLabels[code]} - emplazamiento`,
    coordinates: [-6 + index * 0.5, 36 + index * 0.4],
    rangeKilometres: 240,
    mapZoom: 6.1,
    coverageRing: [
      [-6, 40],
      [-4, 38],
      [-6, 36],
      [-8, 38],
      [-6, 40],
    ],
    validation: {
      status: available
        ? code === 'mu'
          ? 'control-points'
          : 'verified'
        : 'awaiting-data',
      sampleVerified: available,
    },
  };
});

const nationalRadar = {
  id: 'national',
  label: 'Composición nacional',
  kind: 'national',
  cadenceMinutes: 10,
  manifestUrl: '/radar/national/manifest.json',
  available: true,
  latestFrameTime: '2026-07-24T17:30:00Z',
  regionCode: 'PB',
  coverageLabel: 'Península y Baleares',
  includesCanaryIslands: false,
  coordinates: [-3.97, 39.25],
  mapZoom: 4.4,
  coverageRing: [
    [-16.08, 51.3],
    [12.14, 51.3],
    [12.14, 27.22],
    [-16.08, 27.22],
    [-16.08, 51.3],
  ],
  validation: {
    status: 'verified',
    sampleVerified: true,
  },
} as const;

const radars = [nationalRadar, ...regionalRadars];

const radarIndex = {
  schemaVersion: 1,
  generatedAt: '2026-07-24T17:31:00Z',
  radars,
};

const health = {
  schemaVersion: 1,
  generatedAt: '2026-07-24T17:31:00Z',
  status: 'degraded',
  products: radars.map((radar) => ({
    id: radar.id,
    label: radar.label,
    status: radar.available ? 'current' : 'no-data',
    lastFrameTime: radar.latestFrameTime,
    lastPollAt: '2026-07-24T17:31:00Z',
    lastError: null,
  })),
};

const murciaManifest = manifestFor(
  'mu',
  [
    timelineFrame('mu-one', '2026-07-24T17:00:00Z', '1', 'mu'),
    timelineFrame('mu-two', '2026-07-24T17:10:00Z', '2', 'mu'),
    timelineFrame('mu-three', '2026-07-24T17:30:00Z', '3', 'mu'),
  ],
  [
    {
      after: '2026-07-24T17:10:00Z',
      before: '2026-07-24T17:30:00Z',
      expectedCadenceMinutes: 10,
      missingCount: 1,
      expectedTimes: ['2026-07-24T17:20:00Z'],
      timeBasis: 'retrievedAt',
    },
  ],
);
const refreshedMurciaManifest = manifestFor(
  'mu',
  [
    timelineFrame('mu-one', '2026-07-24T17:00:00Z', '1', 'mu'),
    timelineFrame('mu-two', '2026-07-24T17:10:00Z', '2', 'mu'),
    timelineFrame('mu-three', '2026-07-24T17:30:00Z', '3', 'mu'),
    timelineFrame('mu-four', '2026-07-24T17:40:00Z', '4', 'mu'),
  ],
  [
    {
      after: '2026-07-24T17:10:00Z',
      before: '2026-07-24T17:30:00Z',
      expectedCadenceMinutes: 10,
      missingCount: 1,
      expectedTimes: ['2026-07-24T17:20:00Z'],
      timeBasis: 'retrievedAt',
    },
  ],
);
const almeriaManifest = manifestFor('am', [
  timelineFrame('am-only', '2026-07-24T17:30:00Z', 'a', 'am'),
]);
const emptyCorunaManifest = emptyManifestFor('co');
const nationalManifest = {
  ...manifestFor('mu', [
    timelineFrame('national-only', '2026-07-24T17:30:00Z', 'b', 'national'),
  ]),
  radar: {
    id: 'national',
    label: 'Composición nacional',
    kind: 'national',
    cadenceMinutes: 10,
  },
};

describe('App radar', () => {
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    preloadSpy.mockClear();
  });

  it('carga la composición y los 15 radares, y abre Murcia por defecto', async () => {
    mockRadarFetches();

    render(<App />);

    expect(
      await screen.findByRole('heading', { name: 'Radar Murcia' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Fuente radar')).toHaveValue('regional-mu');
    expect(screen.getAllByRole('option')).toHaveLength(16);
    expect(screen.getByText('Últimas 3 h 50 min')).toBeInTheDocument();
    expect(
      await screen.findByText(/Último dato 19:30 · hace/),
    ).toBeInTheDocument();
    expect(screen.queryByText('Hora del producto')).not.toBeInTheDocument();
    expect(screen.queryByText('Hora de obtención')).not.toBeInTheDocument();
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-radar',
      'regional-mu',
    );
    await waitFor(() =>
      expect(screen.getByLabelText('Instante del radar')).toHaveFocus(),
    );
    await waitFor(() => {
      expect(screen.getByTestId('radar-map')).toHaveAttribute(
        'data-frame',
        'mu-three',
      );
    });
    fireEvent.keyDown(screen.getByLabelText('Instante del radar'), {
      key: 'ArrowLeft',
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-two',
    );
  });

  it('conserva la última imagen real al recorrer un hueco', async () => {
    mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });
    const timelineSlider = await screen.findByRole('slider', {
      name: 'Instante del radar',
    });

    fireEvent.change(timelineSlider, { target: { value: '2' } });

    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-two',
    );
    expect(
      screen.getByRole('button', {
        name: 'Sin observación a las 19:20',
      }),
    ).toHaveAttribute('aria-current', 'true');
  });

  it('agrupa los ajustes en un menú contextual accesible', async () => {
    mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    expect(
      screen.queryByRole('group', { name: 'Controles del mapa' }),
    ).not.toBeInTheDocument();
    const trigger = screen.getByRole('button', {
      name: 'Abrir opciones del mapa',
    });
    fireEvent.click(trigger);

    expect(
      screen.getByRole('group', { name: 'Controles del mapa' }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Opacidad del radar'), {
      target: { value: '0.45' },
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-opacity',
      '0.45',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Ver cobertura' }));
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-debug',
      'true',
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(
      screen.queryByRole('group', { name: 'Controles del mapa' }),
    ).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    fireEvent.pointerDown(document.body);
    expect(
      screen.queryByRole('group', { name: 'Controles del mapa' }),
    ).not.toBeInTheDocument();
  });

  it('cambia de producto sin mezclar fotogramas', async () => {
    const fetchMock = mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.change(screen.getByLabelText('Fuente radar'), {
      target: { value: 'regional-am' },
    });

    expect(
      await screen.findByRole('heading', { name: 'Radar Almería' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('radar-map')).toHaveAttribute(
        'data-frame',
        'am-only',
      );
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-radar',
      'regional-am',
    );
    await waitFor(() =>
      expect(screen.getByLabelText('Instante del radar')).toHaveFocus(),
    );
    expect(
      screen.queryByText('3 observaciones reales'),
    ).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      '/radar/regional-am/manifest.json',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('precarga únicamente el timeline seleccionado', async () => {
    mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });
    await waitFor(() => expect(preloadSpy).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('Fuente radar'), {
      target: { value: 'regional-am' },
    });
    await screen.findByRole('heading', { name: 'Radar Almería' });
    await waitFor(() => {
      const lastSlots = preloadSpy.mock.calls.at(-1)?.[0];
      expect(
        lastSlots?.every(
          (slot) =>
            slot.kind === 'gap' ||
            slot.frame.imageUrl.includes('/radar/regional-am/'),
        ),
      ).toBe(true);
    });

    const callsWithData = preloadSpy.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Fuente radar'), {
      target: { value: 'regional-co' },
    });
    await screen.findByText('Sin imágenes disponibles ahora');
    expect(preloadSpy).toHaveBeenCalledTimes(callsWithData);
  });

  it('mantiene seleccionable un radar sin datos y oculta el reproductor', async () => {
    mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.change(screen.getByLabelText('Fuente radar'), {
      target: { value: 'regional-co' },
    });

    expect(
      await screen.findByRole('heading', { name: 'Radar A Coruña' }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText('Sin imágenes disponibles ahora'),
    ).toBeInTheDocument();
    expect(screen.getByText(/seguirá consultándose/)).toBeInTheDocument();
    expect(
      screen.queryByLabelText('Instante del radar'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-radar',
      'regional-co',
    );
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'none',
    );
  });

  it('cambia a la composición nacional sin mezclar productos', async () => {
    const fetchMock = mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.change(screen.getByLabelText('Fuente radar'), {
      target: { value: 'national' },
    });

    expect(
      await screen.findByRole('heading', { name: 'Composición nacional' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Península y Baleares · Canarias usa el radar regional de Las Palmas',
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('radar-map')).toHaveAttribute(
        'data-frame',
        'national-only',
      );
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-radar',
      'national',
    );
    expect(preloadSpy.mock.calls.at(-1)?.[0]).toSatisfy(
      (slots: TimelineSlot[]) =>
        slots.every(
          (slot) =>
            slot.kind === 'gap' ||
            slot.frame.imageUrl.includes('/radar/national/'),
        ),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/radar/national/manifest.json',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('reproduce el historial, cambia de velocidad y acepta flechas', async () => {
    vi.useFakeTimers();
    mockRadarFetches();
    render(<App />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(
      screen.getByRole('heading', { name: 'Radar Murcia' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Rápida' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Reproducir historial' }),
    );
    act(() => {
      vi.advanceTimersByTime(1020);
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-one',
    );
    fireEvent.keyDown(document, { key: 'ArrowRight' });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-two',
    );
    expect(
      screen.getByRole('button', { name: 'Reproducir historial' }),
    ).toBeInTheDocument();
  });

  it('busca nuevos datos cada diez minutos sin interrumpir la exploración', async () => {
    vi.useFakeTimers();
    const fetchMock = mockRadarFetches([
      murciaManifest,
      refreshedMurciaManifest,
      refreshedMurciaManifest,
    ]);
    render(<App />);
    await act(async () => {
      await flushMicrotasks();
    });

    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-three',
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Abrir opciones del mapa' }),
    );
    const opacitySlider = screen.getByLabelText('Opacidad del radar');
    opacitySlider.focus();

    await act(async () => {
      vi.advanceTimersByTime(10 * 60 * 1000);
      await flushMicrotasks();
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-four',
    );

    fireEvent.change(screen.getByLabelText('Instante del radar'), {
      target: { value: '1' },
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-two',
    );

    await act(async () => {
      vi.advanceTimersByTime(10 * 60 * 1000);
      await flushMicrotasks();
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'mu-two',
    );
    expect(
      fetchMock.mock.calls.filter(
        ([url]) => url === '/radar/regional-mu/manifest.json',
      ),
    ).toHaveLength(3);
    expect(opacitySlider).toHaveFocus();
  });

  it('elige localmente el radar regional más cercano', async () => {
    mockRadarFetches();
    const getCurrentPosition = vi
      .fn()
      .mockImplementation((onSuccess: PositionCallback) => {
        onSuccess({
          coords: {
            latitude: 36,
            longitude: -6,
            accuracy: 100,
            altitude: null,
            altitudeAccuracy: null,
            heading: null,
            speed: null,
            toJSON: () => ({}),
          },
          timestamp: Date.now(),
          toJSON: () => ({}),
        });
      });
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Usar mi ubicación para elegir el radar más cercano',
      }),
    );

    expect(
      await screen.findByRole('heading', { name: 'Radar Almería' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Radar más cercano: Almería.')).toBeInTheDocument();
  });

  it('mantiene la interfaz con el último manifiesto válido sin red', async () => {
    seedCache('catalog', radarIndex);
    seedCache('health', health);
    seedCache('manifest:regional-mu', murciaManifest);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));

    render(<App />);

    expect(
      await screen.findByRole('heading', { name: 'Radar Murcia' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/mostrando la última copia válida guardada/),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('radar-map')).toHaveAttribute(
        'data-frame',
        'mu-three',
      ),
    );
    expect(screen.getByText('Retrasado')).toBeInTheDocument();
  });

  it('explica el fallo del catálogo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'No se pudo abrir el catálogo',
      );
    });
  });
});

describe('formatDataAge', () => {
  it('expresa minutos, horas y días sin ocultar la antigüedad', () => {
    const now = Date.parse('2026-07-27T12:00:00Z');
    expect(formatDataAge('2026-07-27T11:59:40Z', now)).toBe(
      'hace menos de 1 min',
    );
    expect(formatDataAge('2026-07-27T09:45:00Z', now)).toBe('hace 2 h 15 min');
    expect(formatDataAge('2026-07-25T10:00:00Z', now)).toBe('hace 2 días 2 h');
  });
});

function manifestFor(
  code: (typeof regionalCodes)[number],
  frames: ReturnType<typeof timelineFrame>[],
  gaps: object[] = [],
) {
  const latest = frames.at(-1)?.time ?? null;
  return {
    schemaVersion: 1,
    radar: {
      id: `regional-${code}`,
      label: radarLabels[code],
      kind: 'regional',
      cadenceMinutes: 10,
    },
    generatedAt: '2026-07-24T17:31:00Z',
    window: {
      hours: 230 / 60,
      minutes: 230,
      start: latest ? '2026-07-24T13:40:00Z' : null,
      end: latest,
      anchor: 'latest-available-frame',
    },
    latestFrameTime: latest,
    latestProductTime: null,
    timeBasis: latest ? 'retrievedAt' : null,
    frames,
    gaps,
    statistics: {
      archivedFrames: frames.length,
      publishedFrames: frames.length,
      discardedDuplicates: 0,
      invalidReports: 0,
    },
  };
}

function emptyManifestFor(code: (typeof regionalCodes)[number]) {
  return manifestFor(code, []);
}

function timelineFrame(
  id: string,
  time: string,
  hashCharacter: string,
  code: string,
) {
  const hash = hashCharacter.repeat(64);
  return {
    id,
    time,
    timeSource: 'retrievedAt',
    productTime: null,
    retrievedAt: time,
    lastRetrievedAt: time,
    sourceHash: `sha256:${hash}`,
    rawUrl:
      code === 'national'
        ? `/raw/national/${hash}.png`
        : `/raw/regional-${code}/${hash}.gif`,
    imageUrl:
      code === 'national'
        ? `/radar/national/frames/${hash}/overlay.png`
        : `/radar/regional-${code}/frames/${hash}/overlay-3857.png`,
    imageCoordinates: [
      [-4, 40],
      [1, 40],
      [1, 36],
      [-4, 36],
    ],
    status: 'available',
  };
}

function mockRadarFetches(murciaManifests: unknown[] = [murciaManifest]) {
  let murciaManifestIndex = 0;
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    let payload: unknown;
    if (input === '/radar/index.json') {
      payload = radarIndex;
    } else if (input === '/status/health.json') {
      payload = health;
    } else if (input === '/radar/regional-mu/manifest.json') {
      payload =
        murciaManifests[
          Math.min(murciaManifestIndex, murciaManifests.length - 1)
        ];
      murciaManifestIndex += 1;
    } else if (input === '/radar/regional-am/manifest.json') {
      payload = almeriaManifest;
    } else if (input === '/radar/regional-co/manifest.json') {
      payload = emptyCorunaManifest;
    } else if (input === '/radar/national/manifest.json') {
      payload = nationalManifest;
    } else {
      throw new Error(`URL inesperada: ${input}`);
    }
    return Promise.resolve({
      ok: true,
      json: async () => payload,
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function flushMicrotasks() {
  for (let iteration = 0; iteration < 8; iteration += 1) {
    await Promise.resolve();
  }
}

function seedCache(cacheId: string, value: unknown) {
  window.localStorage.setItem(
    cacheKey(cacheId),
    JSON.stringify({
      schemaVersion: 1,
      savedAt: '2026-07-27T12:00:00Z',
      value,
    }),
  );
}
