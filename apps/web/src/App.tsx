import { useEffect, useState } from 'react';

import { RadarMap } from './RadarMap';
import {
  FRAME_REPORT_URL,
  isRadarFrameReport,
  type RadarFrameReport,
} from './radarFrame';

export function App() {
  const [frame, setFrame] = useState<RadarFrameReport | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [opacity, setOpacity] = useState(0.72);
  const [showDebug, setShowDebug] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    async function loadFrame() {
      try {
        const response = await fetch(FRAME_REPORT_URL, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error('No se pudo cargar el informe.');
        }
        const payload: unknown = await response.json();
        if (!isRadarFrameReport(payload)) {
          throw new Error('El informe no cumple el contrato.');
        }
        setFrame(payload);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setLoadError(true);
        }
      }
    }

    void loadFrame();
    return () => controller.abort();
  }, []);

  return (
    <main className="radar-app">
      <header className="topbar">
        <div>
          <p className="eyebrow">Calibración geográfica · Fase 4</p>
          <h1>Radar Murcia</h1>
        </div>
        <a
          className="aemet-credit"
          href="https://www.aemet.es/es/eltiempo/observacion/radar/ayuda"
          target="_blank"
          rel="noreferrer"
        >
          Datos radar © AEMET
        </a>
      </header>

      <section className="map-layout" aria-label="Visor de calibración">
        {frame ? (
          <>
            <RadarMap frame={frame} opacity={opacity} showDebug={showDebug} />
            <aside className="calibration-panel" aria-labelledby="panel-title">
              <div className="panel-heading">
                <p className="status-chip">Calibración válida</p>
                <h2 id="panel-title">Murcia–Fortuna</h2>
                <p>
                  Una capa real reproyectada a Web Mercator, sin interpolar
                  clases de reflectividad.
                </p>
              </div>

              <dl className="metrics">
                <div>
                  <dt>Error medio</dt>
                  <dd>
                    {formatKilometres(frame.calibration.meanErrorKilometres)}
                  </dd>
                </div>
                <div>
                  <dt>Error máximo</dt>
                  <dd>
                    {formatKilometres(frame.calibration.maximumErrorKilometres)}
                  </dd>
                </div>
                <div>
                  <dt>Controles</dt>
                  <dd>{frame.calibration.controlPointCount}</dd>
                </div>
                <div>
                  <dt>Raster</dt>
                  <dd>
                    {frame.output.width}×{frame.output.height}
                  </dd>
                </div>
              </dl>

              <label className="opacity-control">
                <span>
                  Opacidad
                  <output>{Math.round(opacity * 100)}%</output>
                </span>
                <input
                  aria-label="Opacidad del radar"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={opacity}
                  onChange={(event) =>
                    setOpacity(Number(event.currentTarget.value))
                  }
                />
              </label>

              <button
                className="debug-toggle"
                type="button"
                aria-pressed={showDebug}
                onClick={() => setShowDebug((visible) => !visible)}
              >
                <span aria-hidden="true" className="toggle-indicator" />
                {showDebug
                  ? 'Ocultar puntos de control'
                  : 'Mostrar puntos de control'}
              </button>

              <div className="legend-note">
                <span className="legend-line" aria-hidden="true" />
                <p>
                  Círculo nominal de 240 km y cruces provinciales de referencia
                  AEMET/IGN.
                </p>
              </div>
            </aside>
          </>
        ) : (
          <div className="initial-state" role={loadError ? 'alert' : 'status'}>
            <p className="eyebrow">Radar Murcia–Fortuna</p>
            <h2>
              {loadError
                ? 'No se pudo abrir la muestra'
                : 'Preparando el mapa…'}
            </h2>
            <p>
              {loadError
                ? 'Comprueba que Vite está sirviendo los archivos públicos de la fase 4.'
                : 'Cargando la reproyección y sus puntos de control.'}
            </p>
          </div>
        )}
      </section>
    </main>
  );
}

function formatKilometres(value: number) {
  return `${value.toLocaleString('es-ES', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  })} km`;
}
