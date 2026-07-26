import { useEffect, useMemo, useRef, useState } from 'react';

import { preloadInPriorityOrder } from './framePreloader';
import { RadarMap } from './RadarMap';
import {
  FRAME_REPORT_URL,
  isRadarFrameReport,
  type RadarFrameReport,
} from './radarFrame';
import {
  buildTimelineSlots,
  formatMadridDate,
  formatMadridTime,
  HISTORY_HOURS,
  isRadarManifest,
  MANIFEST_URL,
  type RadarManifest,
  type TimelineSlot,
} from './radarManifest';

const SPEEDS = {
  slow: { label: 'Lenta', milliseconds: 1500 },
  normal: { label: 'Normal', milliseconds: 850 },
  fast: { label: 'Rápida', milliseconds: 420 },
} as const;
const LAST_FRAME_PAUSE_FACTOR = 2.4;

type PlaybackSpeed = keyof typeof SPEEDS;

interface RadarData {
  manifest: RadarManifest;
  calibration: RadarFrameReport;
}

export function App() {
  const [data, setData] = useState<RadarData | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>('normal');
  const [opacity, setOpacity] = useState(0.72);
  const [showDebug, setShowDebug] = useState(false);
  const selectedButtonRef = useRef<HTMLButtonElement | null>(null);
  const reducedMotion = useReducedMotion();
  const slots = useMemo(
    () => (data ? buildTimelineSlots(data.manifest) : []),
    [data],
  );
  const selectedSlot = slots[selectedIndex] ?? null;

  useEffect(() => {
    const controller = new AbortController();

    async function loadRadarData() {
      try {
        const [manifestResponse, calibrationResponse] = await Promise.all([
          fetch(MANIFEST_URL, { signal: controller.signal }),
          fetch(FRAME_REPORT_URL, { signal: controller.signal }),
        ]);
        if (!manifestResponse.ok || !calibrationResponse.ok) {
          throw new Error('No se pudieron cargar los datos publicados.');
        }
        const [manifest, calibration]: [unknown, unknown] = await Promise.all([
          manifestResponse.json(),
          calibrationResponse.json(),
        ]);
        if (!isRadarManifest(manifest) || !isRadarFrameReport(calibration)) {
          throw new Error('Los datos publicados no cumplen el contrato.');
        }
        const loaded: RadarData = { manifest, calibration };
        const loadedSlots = buildTimelineSlots(manifest);
        setData(loaded);
        setSelectedIndex(loadedSlots.length - 1);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setLoadError(true);
        }
      }
    }

    void loadRadarData();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (slots.length === 0) {
      return;
    }
    return preloadInPriorityOrder(slots, selectedIndex);
  }, [selectedIndex, slots]);

  useEffect(() => {
    const button = selectedButtonRef.current;
    if (button && typeof button.scrollIntoView === 'function') {
      button.scrollIntoView({
        block: 'nearest',
        inline: 'center',
        behavior: reducedMotion ? 'auto' : 'smooth',
      });
    }
  }, [reducedMotion, selectedIndex]);

  useEffect(() => {
    if (!playing || slots.length < 2) {
      return;
    }
    const atLatest = selectedIndex === slots.length - 1;
    const delay =
      SPEEDS[speed].milliseconds * (atLatest ? LAST_FRAME_PAUSE_FACTOR : 1);
    const timer = window.setTimeout(() => {
      setSelectedIndex((current) =>
        current >= slots.length - 1 ? 0 : current + 1,
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [playing, selectedIndex, slots.length, speed]);

  useEffect(() => {
    function navigateWithKeyboard(event: KeyboardEvent) {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLButtonElement ||
        target instanceof HTMLSelectElement ||
        target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        setPlaying(false);
        setSelectedIndex((current) => Math.max(0, current - 1));
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        setPlaying(false);
        setSelectedIndex((current) => Math.min(slots.length - 1, current + 1));
      }
    }
    document.addEventListener('keydown', navigateWithKeyboard);
    return () => document.removeEventListener('keydown', navigateWithKeyboard);
  }, [slots.length]);

  function selectSlot(index: number) {
    setPlaying(false);
    setSelectedIndex(index);
  }

  if (!data || !selectedSlot) {
    return (
      <main className="radar-app radar-app--initial">
        <div className="initial-state" role={loadError ? 'alert' : 'status'}>
          <p className="eyebrow">Radar Murcia–Fortuna</p>
          <h1>
            {loadError
              ? 'No se pudo abrir el historial'
              : 'Preparando tres horas de radar…'}
          </h1>
          <p>
            {loadError
              ? 'Comprueba que el manifiesto y sus imágenes derivadas estén publicados.'
              : 'Cargando primero la observación más reciente.'}
          </p>
        </div>
      </main>
    );
  }

  const selectedFrame =
    selectedSlot.kind === 'frame' ? selectedSlot.frame : null;
  const isLatest =
    selectedSlot.kind === 'frame' &&
    selectedSlot.time === data.manifest.latestFrameTime;
  const currentTime = formatMadridTime(selectedSlot.time);
  const firstSlot = slots[0]!;
  const lastSlot = slots.at(-1)!;
  const playbackAnnouncement = playing
    ? `Reproduciendo a velocidad ${SPEEDS[speed].label.toLowerCase()}. ${slotAnnouncement(selectedSlot)}`
    : `En pausa. ${slotAnnouncement(selectedSlot)}`;

  return (
    <main className="radar-app">
      <header className="topbar">
        <div>
          <p className="eyebrow">Últimas {HISTORY_HOURS} horas</p>
          <h1>Radar Murcia</h1>
        </div>
        <div className="header-meta">
          <span>{data.manifest.frames.length} observaciones reales</span>
          <a
            className="aemet-credit"
            href="https://www.aemet.es/es/eltiempo/observacion/radar/ayuda"
            target="_blank"
            rel="noreferrer"
          >
            Datos radar © AEMET
          </a>
        </div>
      </header>

      <section
        className="map-layout"
        aria-label="Reproductor del radar de Murcia"
      >
        <RadarMap
          calibration={data.calibration}
          selectedFrame={selectedFrame}
          opacity={opacity}
          showDebug={showDebug}
          reducedMotion={reducedMotion}
        />

        <div className={`frame-card${selectedFrame ? '' : ' frame-card--gap'}`}>
          <p className="frame-card__label">
            {selectedFrame
              ? selectedFrame.timeSource === 'productTime'
                ? 'Hora del producto'
                : 'Hora de obtención'
              : 'Hueco temporal'}
          </p>
          <div className="frame-card__time">
            <time dateTime={selectedSlot.time}>{currentTime}</time>
            {isLatest && <span>Más reciente</span>}
          </div>
          <p>
            {formatMadridDate(selectedSlot.time)} · Europe/Madrid
            {selectedFrame?.timeSource === 'retrievedAt'
              ? ' · producto sin hora verificable'
              : ''}
          </p>
          {!selectedFrame && (
            <strong>No existe una observación para este intervalo.</strong>
          )}
        </div>

        <div className="map-tools" aria-label="Ajustes del mapa">
          <label>
            <span>Opacidad</span>
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
            <output>{Math.round(opacity * 100)}%</output>
          </label>
          <button
            type="button"
            aria-pressed={showDebug}
            onClick={() => setShowDebug((visible) => !visible)}
          >
            {showDebug ? 'Ocultar calibración' : 'Ver calibración'}
          </button>
        </div>

        <section className="timeline-panel" aria-label="Controles temporales">
          <div className="playback-row">
            <button
              className="play-button"
              type="button"
              aria-label={
                playing ? 'Pausar reproducción' : 'Reproducir historial'
              }
              aria-pressed={playing}
              onClick={() => setPlaying((active) => !active)}
            >
              <span aria-hidden="true">{playing ? 'Ⅱ' : '▶'}</span>
            </button>

            <label className="timeline-slider">
              <span className="visually-hidden">Instante del radar</span>
              <input
                aria-label="Instante del radar"
                aria-valuetext={slotAnnouncement(selectedSlot)}
                type="range"
                min="0"
                max={slots.length - 1}
                step="1"
                value={selectedIndex}
                onChange={(event) =>
                  selectSlot(Number(event.currentTarget.value))
                }
              />
              <span className="timeline-range">
                <time dateTime={firstSlot.time}>
                  {formatMadridTime(firstSlot.time)}
                </time>
                <span>{HISTORY_HOURS} h</span>
                <time dateTime={lastSlot.time}>
                  {formatMadridTime(lastSlot.time)}
                </time>
              </span>
            </label>

            <div className="speed-control" role="group" aria-label="Velocidad">
              {(Object.keys(SPEEDS) as PlaybackSpeed[]).map((value) => (
                <button
                  type="button"
                  key={value}
                  aria-pressed={speed === value}
                  onClick={() => setSpeed(value)}
                >
                  {SPEEDS[value].label}
                </button>
              ))}
            </div>
          </div>

          <div className="frame-strip" aria-label="Observaciones e intervalos">
            {slots.map((slot, index) => {
              const latest =
                slot.kind === 'frame' &&
                slot.time === data.manifest.latestFrameTime;
              const selected = index === selectedIndex;
              return (
                <button
                  className={`frame-button frame-button--${slot.kind}`}
                  type="button"
                  key={slot.id}
                  ref={selected ? selectedButtonRef : undefined}
                  aria-current={selected ? 'true' : undefined}
                  aria-label={
                    slot.kind === 'gap'
                      ? `Sin observación a las ${formatMadridTime(slot.time)}`
                      : `Mostrar observación de las ${formatMadridTime(slot.time)}${latest ? ', la más reciente' : ''}`
                  }
                  onClick={() => selectSlot(index)}
                >
                  <span className="frame-button__dot" aria-hidden="true" />
                  <time dateTime={slot.time}>
                    {formatMadridTime(slot.time)}
                  </time>
                  {latest && <small>Ahora</small>}
                  {slot.kind === 'gap' && <small>Sin dato</small>}
                </button>
              );
            })}
          </div>

          <footer className="timeline-footer">
            <p>
              <span className="legend-dot" aria-hidden="true" />
              Observación real
              <span className="legend-gap" aria-hidden="true" />
              Hueco sin interpolar
            </p>
            <p>← → para recorrer · pausa al cerrar el bucle</p>
          </footer>
        </section>

        <p className="visually-hidden" aria-live="polite">
          {playbackAnnouncement}
        </p>
      </section>
    </main>
  );
}

function slotAnnouncement(slot: TimelineSlot): string {
  const time = formatMadridTime(slot.time);
  return slot.kind === 'frame'
    ? `Observación de las ${time}`
    : `Sin observación a las ${time}`;
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return;
    }
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return reduced;
}
