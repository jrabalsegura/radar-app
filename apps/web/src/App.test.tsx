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
import type { RegionalRadarIndexEntry } from './radarIndex';
import type { RadarTimelineFrame, TimelineSlot } from './radarManifest';

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
    radar: RegionalRadarIndexEntry;
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

const radars = regionalCodes.map((code, index) => {
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
const almeriaManifest = manifestFor('am', [
  timelineFrame('am-only', '2026-07-24T17:30:00Z', 'a', 'am'),
]);
const emptyCorunaManifest = emptyManifestFor('co');

describe('App regional', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    preloadSpy.mockClear();
  });

  it('carga los 15 radares y abre Murcia por defecto', async () => {
    mockRadarFetches();

    render(<App />);

    expect(
      await screen.findByRole('heading', { name: 'Radar Murcia' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Radar regional')).toHaveValue('regional-mu');
    expect(screen.getAllByRole('option')).toHaveLength(15);
    expect(screen.getByText('Últimas 3 h 50 min')).toBeInTheDocument();
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-radar',
      'regional-mu',
    );
    await waitFor(() => {
      expect(screen.getByTestId('radar-map')).toHaveAttribute(
        'data-frame',
        'mu-three',
      );
    });
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
      screen.getByText(/Se mantiene la última reflectividad disponible/),
    ).toHaveTextContent('19:10');
  });

  it('cambia de producto sin mezclar fotogramas', async () => {
    const fetchMock = mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.change(screen.getByLabelText('Radar regional'), {
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

    fireEvent.change(screen.getByLabelText('Radar regional'), {
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
    fireEvent.change(screen.getByLabelText('Radar regional'), {
      target: { value: 'regional-co' },
    });
    await screen.findByText('Sin imágenes disponibles ahora');
    expect(preloadSpy).toHaveBeenCalledTimes(callsWithData);
  });

  it('mantiene seleccionable un radar sin datos y oculta el reproductor', async () => {
    mockRadarFetches();
    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.change(screen.getByLabelText('Radar regional'), {
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
    rawUrl: `/raw/regional-${code}/${hash}.gif`,
    imageUrl: `/radar/regional-${code}/frames/${hash}/overlay-3857.png`,
    imageCoordinates: [
      [-4, 40],
      [1, 40],
      [1, 36],
      [-4, 36],
    ],
    status: 'available',
  };
}

function mockRadarFetches() {
  const fetchMock = vi.fn().mockImplementation((input: string) => {
    let payload: unknown;
    if (input === '/radar/index.json') {
      payload = radarIndex;
    } else if (input === '/status/health.json') {
      payload = health;
    } else if (input === '/radar/regional-mu/manifest.json') {
      payload = murciaManifest;
    } else if (input === '/radar/regional-am/manifest.json') {
      payload = almeriaManifest;
    } else if (input === '/radar/regional-co/manifest.json') {
      payload = emptyCorunaManifest;
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
