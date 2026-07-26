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
import type { RadarTimelineFrame } from './radarManifest';

vi.mock('./RadarMap', () => ({
  RadarMap: ({
    selectedFrame,
    opacity,
    showDebug,
    reducedMotion,
  }: {
    selectedFrame: RadarTimelineFrame | null;
    opacity: number;
    showDebug: boolean;
    reducedMotion: boolean;
  }) => (
    <div
      data-testid="radar-map"
      data-frame={selectedFrame?.id ?? 'gap'}
      data-opacity={opacity}
      data-debug={showDebug}
      data-reduced-motion={reducedMotion}
    />
  ),
}));

const calibration = {
  attribution: 'Datos radar © AEMET',
  radar: {
    aemetCode: 'FTN',
    name: 'Murcia - Fortuna',
    coordinates: [-1.18970006, 38.26438295],
    rangeKilometres: 240,
  },
  output: {
    file: 'overlay-3857.png',
    width: 630,
    height: 618,
    crs: 'EPSG:3857',
    pixelSizeMetres: 1000,
    maplibreCoordinates: [
      [-4, 40],
      [1, 40],
      [1, 36],
      [-4, 36],
    ],
  },
  calibration: {
    status: 'pass',
    controlPointCount: 8,
    meanErrorKilometres: 0.368942,
    maximumErrorKilometres: 0.699806,
    acceptedMaximumErrorPixels: 1,
    controlPoints: [
      {
        id: 'one',
        label: 'Punto uno',
        coordinates: [-2.7, 39.3],
        errorKilometres: 0.2,
      },
    ],
  },
  debug: {
    coverageRing: [
      [-1, 40],
      [1, 38],
      [-1, 36],
      [-3, 38],
      [-1, 40],
    ],
  },
};

const frames = [
  timelineFrame('one', '2026-07-24T17:00:00Z', '1'),
  timelineFrame('two', '2026-07-24T17:10:00Z', '2'),
  timelineFrame('three', '2026-07-24T17:30:00Z', '3'),
];

const manifest = {
  schemaVersion: 1,
  radar: {
    id: 'regional-mu',
    label: 'Murcia',
    kind: 'regional',
    cadenceMinutes: 10,
  },
  generatedAt: '2026-07-24T17:31:00Z',
  window: {
    hours: 3,
    start: '2026-07-24T14:30:00Z',
    end: '2026-07-24T17:30:00Z',
    anchor: 'latest-available-frame',
  },
  latestFrameTime: '2026-07-24T17:30:00Z',
  latestProductTime: null,
  timeBasis: 'retrievedAt',
  frames,
  gaps: [
    {
      after: '2026-07-24T17:10:00Z',
      before: '2026-07-24T17:30:00Z',
      expectedCadenceMinutes: 10,
      missingCount: 1,
      expectedTimes: ['2026-07-24T17:20:00Z'],
      timeBasis: 'retrievedAt',
    },
  ],
  statistics: {
    archivedFrames: 9,
    publishedFrames: 3,
    discardedDuplicates: 1,
    invalidReports: 0,
  },
};

describe('App', () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('carga el manifiesto real y abre la observación más reciente', async () => {
    mockRadarFetches();

    render(<App />);

    expect(
      await screen.findByRole('heading', { name: 'Radar Murcia' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Últimas 3 horas')).toBeInTheDocument();
    expect(screen.getByText('3 observaciones reales')).toBeInTheDocument();
    expect(screen.getByText('Más reciente')).toBeInTheDocument();
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'three',
    );
    expect(
      screen.getByRole('slider', { name: 'Instante del radar' }),
    ).toHaveValue('3');
  });

  it('mantiene controles y texto sincronizados y conserva la última imagen en un hueco', async () => {
    mockRadarFetches();

    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Mostrar observación de las 19:00',
      }),
    );
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'one',
    );
    expect(
      screen.getByRole('slider', { name: 'Instante del radar' }),
    ).toHaveValue('0');

    fireEvent.change(
      screen.getByRole('slider', { name: 'Instante del radar' }),
      {
        target: { value: '2' },
      },
    );
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'two',
    );
    expect(
      screen.getByText('No existe una observación para este intervalo.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Se mantiene la última reflectividad disponible/),
    ).toHaveTextContent('19:10');
    expect(
      screen.getByRole('slider', { name: 'Instante del radar' }),
    ).toHaveAttribute(
      'aria-valuetext',
      'Sin observación a las 19:20. Se mantiene la reflectividad de las 19:10.',
    );
    expect(screen.getAllByText('19:20')).toHaveLength(2);
  });

  it('reproduce, cambia de velocidad, pausa al final y acepta flechas', async () => {
    vi.useFakeTimers();
    mockRadarFetches();

    render(<App />);
    await act(async () => {
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
    expect(
      screen.getByRole('button', { name: 'Pausar reproducción' }),
    ).toHaveAttribute('aria-pressed', 'true');

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'three',
    );
    act(() => {
      vi.advanceTimersByTime(20);
    });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'one',
    );

    fireEvent.keyDown(document, { key: 'ArrowRight' });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-frame',
      'two',
    );
    expect(
      screen.getByRole('button', { name: 'Reproducir historial' }),
    ).toBeInTheDocument();
  });

  it('permite ajustar opacidad y mostrar la calibración', async () => {
    mockRadarFetches();

    render(<App />);
    await screen.findByRole('heading', { name: 'Radar Murcia' });

    fireEvent.change(screen.getByLabelText('Opacidad del radar'), {
      target: { value: '0.4' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ver calibración' }));
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-opacity',
      '0.4',
    );
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-debug',
      'true',
    );
  });

  it('desactiva las transiciones cuando el sistema pide movimiento reducido', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    );
    mockRadarFetches();

    render(<App />);

    await screen.findByRole('heading', { name: 'Radar Murcia' });
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-reduced-motion',
      'true',
    );
  });

  it('explica el fallo cuando el manifiesto no se puede cargar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'No se pudo abrir el historial',
      );
    });
  });
});

function timelineFrame(id: string, time: string, hashCharacter: string) {
  const hash = hashCharacter.repeat(64);
  return {
    id,
    time,
    timeSource: 'retrievedAt',
    productTime: null,
    retrievedAt: time,
    lastRetrievedAt: time,
    sourceHash: `sha256:${hash}`,
    rawUrl: `/raw/regional-mu/${hash}.gif`,
    imageUrl: `/radar/regional-mu/frames/${hash}/overlay-3857.png`,
    status: 'available',
  };
}

function mockRadarFetches() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          input.endsWith('manifest.json') ? manifest : calibration,
      }),
    ),
  );
}
