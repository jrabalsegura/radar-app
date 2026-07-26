import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

vi.mock('./RadarMap', () => ({
  RadarMap: ({
    opacity,
    showDebug,
  }: {
    opacity: number;
    showDebug: boolean;
  }) => (
    <div
      data-testid="radar-map"
      data-opacity={opacity}
      data-debug={showDebug}
    />
  ),
}));

const frame = {
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

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('muestra la capa calibrada, sus métricas y los controles de depuración', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => frame,
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole('heading', { name: 'Radar Murcia' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('0,369 km')).toBeInTheDocument();
    expect(screen.getByText('0,700 km')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Datos radar © AEMET' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-opacity',
      '0.72',
    );
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-debug',
      'true',
    );

    fireEvent.change(screen.getByLabelText('Opacidad del radar'), {
      target: { value: '0.4' },
    });
    expect(screen.getByText('40%')).toBeInTheDocument();
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-opacity',
      '0.4',
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'Ocultar puntos de control' }),
    );
    expect(screen.getByTestId('radar-map')).toHaveAttribute(
      'data-debug',
      'false',
    );
  });

  it('explica el fallo cuando el informe no se puede cargar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert', { name: '' })).toHaveTextContent(
        'No se pudo abrir la muestra',
      );
    });
  });
});
