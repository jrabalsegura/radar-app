import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';

import { preloadInPriorityOrder } from './framePreloader';
import { RadarMap } from './RadarMap';
import {
  isRadarHealth,
  RADAR_HEALTH_URL,
  type RadarHealth,
  type RadarHealthStatus,
} from './radarHealth';
import {
  isRadarIndex,
  RADAR_INDEX_URL,
  type RadarIndex,
  type RegionalRadarIndexEntry,
} from './radarIndex';
import {
  buildTimelineSlots,
  formatMadridDate,
  formatMadridTime,
  HISTORY_HOURS,
  isRadarManifest,
  type RadarManifest,
  type RadarTimelineFrame,
  type TimelineSlot,
} from './radarManifest';

const SPEEDS = {
  slow: { label: 'Lenta', milliseconds: 1500 },
  normal: { label: 'Normal', milliseconds: 850 },
  fast: { label: 'Rápida', milliseconds: 420 },
} as const;
const LAST_FRAME_PAUSE_FACTOR = 2.4;
const PREFERRED_RADAR_ID = 'regional-mu';

type PlaybackSpeed = keyof typeof SPEEDS;

export function App() {
  const [index, setIndex] = useState<RadarIndex | null>(null);
  const [health, setHealth] = useState<RadarHealth | null>(null);
  const [selectedRadarId, setSelectedRadarId] = useState('');
  const [manifest, setManifest] = useState<RadarManifest | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [manifestError, setManifestError] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>('normal');
  const [opacity, setOpacity] = useState(0.72);
  const [showDebug, setShowDebug] = useState(false);
  const selectedButtonRef = useRef<HTMLButtonElement | null>(null);
  const reducedMotion = useReducedMotion();
  const selectedRadar =
    index?.radars.find((radar) => radar.id === selectedRadarId) ?? null;
  const selectedHealth =
    health?.products.find((product) => product.id === selectedRadarId) ?? null;
  const slots = useMemo(
    () => (manifest ? buildTimelineSlots(manifest) : []),
    [manifest],
  );
  const selectedSlot = slots[selectedIndex] ?? null;

  useEffect(() => {
    const controller = new AbortController();

    async function loadCatalog() {
      try {
        const [indexResponse, healthResponse] = await Promise.all([
          fetch(RADAR_INDEX_URL, { signal: controller.signal }),
          fetch(RADAR_HEALTH_URL, { signal: controller.signal }),
        ]);
        if (!indexResponse.ok || !healthResponse.ok) {
          throw new Error('No se pudo cargar el catálogo regional.');
        }
        const [indexPayload, healthPayload]: [unknown, unknown] =
          await Promise.all([indexResponse.json(), healthResponse.json()]);
        if (!isRadarIndex(indexPayload) || !isRadarHealth(healthPayload)) {
          throw new Error('El catálogo regional no cumple el contrato.');
        }
        setIndex(indexPayload);
        setHealth(healthPayload);
        const preferred = indexPayload.radars.find(
          (radar) => radar.id === PREFERRED_RADAR_ID,
        );
        setSelectedRadarId(preferred?.id ?? indexPayload.radars[0]?.id ?? '');
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setCatalogError(true);
        }
      }
    }

    void loadCatalog();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedRadar) {
      return;
    }
    const controller = new AbortController();

    async function loadManifest(radar: RegionalRadarIndexEntry) {
      try {
        const response = await fetch(radar.manifestUrl, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error('No se pudo cargar el historial seleccionado.');
        }
        const payload: unknown = await response.json();
        if (!isRadarManifest(payload) || payload.radar.id !== radar.id) {
          throw new Error('El historial no cumple el contrato regional.');
        }
        setManifest(payload);
        setSelectedIndex(Math.max(0, buildTimelineSlots(payload).length - 1));
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setManifestError(true);
        }
      }
    }

    void loadManifest(selectedRadar);
    return () => controller.abort();
  }, [selectedRadar]);

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
        setSelectedIndex((current) =>
          Math.min(Math.max(0, slots.length - 1), current + 1),
        );
      }
    }
    document.addEventListener('keydown', navigateWithKeyboard);
    return () => document.removeEventListener('keydown', navigateWithKeyboard);
  }, [slots.length]);

  if (!index || !selectedRadar) {
    return (
      <main className="radar-app radar-app--initial">
        <div className="initial-state" role={catalogError ? 'alert' : 'status'}>
          <p className="eyebrow">Red regional AEMET</p>
          <h1>
            {catalogError
              ? 'No se pudo abrir el catálogo'
              : 'Preparando los radares regionales…'}
          </h1>
          <p>
            {catalogError
              ? 'Comprueba que el índice y el estado operativo estén publicados.'
              : 'Cargando los 15 emplazamientos y su estado actual.'}
          </p>
        </div>
      </main>
    );
  }

  const selectedFrame =
    selectedSlot?.kind === 'frame' ? selectedSlot.frame : null;
  const mapFrame = selectedSlot ? mostRecentFrame(slots, selectedIndex) : null;
  const status = selectedHealth?.status ?? radarAvailability(selectedRadar);

  function selectSlot(indexValue: number) {
    setPlaying(false);
    setSelectedIndex(indexValue);
  }

  return (
    <main className="radar-app">
      <header className="topbar">
        <div className="radar-heading">
          <p className="eyebrow">Últimas {HISTORY_HOURS} horas</p>
          <div className="radar-title-row">
            <h1>Radar {selectedRadar.label}</h1>
            <span className={`status-chip status-chip--${status}`}>
              {statusLabel(status)}
            </span>
          </div>
        </div>

        <div className="radar-selector">
          <label htmlFor="regional-radar">Radar regional</label>
          <select
            id="regional-radar"
            value={selectedRadar.id}
            onChange={(event) => {
              setManifest(null);
              setManifestError(false);
              setPlaying(false);
              setSelectedIndex(0);
              setSelectedRadarId(event.currentTarget.value);
            }}
          >
            {index.radars.map((radar) => (
              <option key={radar.id} value={radar.id}>
                {radar.label}
                {radar.available ? '' : ' · sin datos'}
              </option>
            ))}
          </select>
          <span>{selectedRadar.siteName}</span>
        </div>

        <div className="header-meta">
          <span>
            {manifest
              ? `${manifest.frames.length} ${
                  manifest.frames.length === 1
                    ? 'observación real'
                    : 'observaciones reales'
                }`
              : 'Cargando historial…'}
          </span>
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
        aria-label={`Reproductor del radar de ${selectedRadar.label}`}
      >
        <RadarMap
          key={selectedRadar.id}
          radar={selectedRadar}
          selectedFrame={mapFrame}
          opacity={opacity}
          showDebug={showDebug}
          reducedMotion={reducedMotion}
        />

        {selectedSlot && manifest ? (
          <FrameCard
            manifest={manifest}
            selectedSlot={selectedSlot}
            selectedFrame={selectedFrame}
            mapFrame={mapFrame}
          />
        ) : (
          <div
            className={`no-data-card${manifestError ? ' no-data-card--error' : ''}`}
            role={manifestError ? 'alert' : 'status'}
          >
            <p className="frame-card__label">{selectedRadar.siteCode}</p>
            <h2>
              {manifestError
                ? 'No se pudo abrir este historial'
                : manifest
                  ? 'Sin imágenes disponibles ahora'
                  : 'Cargando historial…'}
            </h2>
            <p>
              {manifestError
                ? 'El resto de radares sigue disponible. Puedes seleccionar otro emplazamiento.'
                : manifest
                  ? 'Este radar permanece configurado y seguirá consultándose. Las imágenes aparecerán automáticamente cuando AEMET vuelva a publicarlas.'
                  : 'El mapa ya está centrado en el emplazamiento seleccionado.'}
            </p>
          </div>
        )}

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
              disabled={!mapFrame}
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
            {showDebug ? 'Ocultar cobertura' : 'Ver cobertura'}
          </button>
        </div>

        {selectedSlot && manifest && (
          <Timeline
            manifest={manifest}
            slots={slots}
            selectedIndex={selectedIndex}
            selectedSlot={selectedSlot}
            mapFrame={mapFrame}
            playing={playing}
            speed={speed}
            selectedButtonRef={selectedButtonRef}
            onSelect={selectSlot}
            onTogglePlaying={() => setPlaying((active) => !active)}
            onSpeed={setSpeed}
          />
        )}
      </section>
    </main>
  );
}

interface FrameCardProps {
  manifest: RadarManifest;
  selectedSlot: TimelineSlot;
  selectedFrame: RadarTimelineFrame | null;
  mapFrame: RadarTimelineFrame | null;
}

function FrameCard({
  manifest,
  selectedSlot,
  selectedFrame,
  mapFrame,
}: FrameCardProps) {
  const isLatest =
    selectedSlot.kind === 'frame' &&
    selectedSlot.time === manifest.latestFrameTime;
  return (
    <div
      className={`frame-card${selectedSlot.kind === 'gap' ? ' frame-card--gap' : ''}`}
    >
      <p className="frame-card__label">
        {selectedFrame
          ? selectedFrame.timeSource === 'productTime'
            ? 'Hora del producto'
            : 'Hora de obtención'
          : 'Hueco temporal'}
      </p>
      <div className="frame-card__time">
        <time dateTime={selectedSlot.time}>
          {formatMadridTime(selectedSlot.time)}
        </time>
        {isLatest && <span>Más reciente</span>}
      </div>
      <p>
        {formatMadridDate(selectedSlot.time)} · Europe/Madrid
        {selectedFrame?.timeSource === 'retrievedAt'
          ? ' · producto sin hora verificable'
          : ''}
      </p>
      {!selectedFrame && (
        <>
          <strong>No existe una observación para este intervalo.</strong>
          {mapFrame && (
            <p className="frame-card__continuity">
              Se mantiene la última reflectividad disponible, de las{' '}
              <time dateTime={mapFrame.time}>
                {formatMadridTime(mapFrame.time)}
              </time>
              .
            </p>
          )}
        </>
      )}
    </div>
  );
}

interface TimelineProps {
  manifest: RadarManifest;
  slots: TimelineSlot[];
  selectedIndex: number;
  selectedSlot: TimelineSlot;
  mapFrame: RadarTimelineFrame | null;
  playing: boolean;
  speed: PlaybackSpeed;
  selectedButtonRef: RefObject<HTMLButtonElement | null>;
  onSelect: (index: number) => void;
  onTogglePlaying: () => void;
  onSpeed: (speed: PlaybackSpeed) => void;
}

function Timeline({
  manifest,
  slots,
  selectedIndex,
  selectedSlot,
  mapFrame,
  playing,
  speed,
  selectedButtonRef,
  onSelect,
  onTogglePlaying,
  onSpeed,
}: TimelineProps) {
  const firstSlot = slots[0]!;
  const lastSlot = slots.at(-1)!;
  const playbackAnnouncement = playing
    ? `Reproduciendo a velocidad ${SPEEDS[speed].label.toLowerCase()}. ${slotAnnouncement(selectedSlot, mapFrame)}`
    : `En pausa. ${slotAnnouncement(selectedSlot, mapFrame)}`;
  return (
    <section className="timeline-panel" aria-label="Controles temporales">
      <div className="playback-row">
        <button
          className="play-button"
          type="button"
          aria-label={playing ? 'Pausar reproducción' : 'Reproducir historial'}
          aria-pressed={playing}
          onClick={onTogglePlaying}
        >
          <span aria-hidden="true">{playing ? 'Ⅱ' : '▶'}</span>
        </button>

        <label className="timeline-slider">
          <span className="visually-hidden">Instante del radar</span>
          <input
            aria-label="Instante del radar"
            aria-valuetext={slotAnnouncement(selectedSlot, mapFrame)}
            type="range"
            min="0"
            max={slots.length - 1}
            step="1"
            value={selectedIndex}
            onChange={(event) => onSelect(Number(event.currentTarget.value))}
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
              onClick={() => onSpeed(value)}
            >
              {SPEEDS[value].label}
            </button>
          ))}
        </div>
      </div>

      <div className="frame-strip" aria-label="Observaciones e intervalos">
        {slots.map((slot, index) => {
          const latest =
            slot.kind === 'frame' && slot.time === manifest.latestFrameTime;
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
              onClick={() => onSelect(index)}
            >
              <span className="frame-button__dot" aria-hidden="true" />
              <time dateTime={slot.time}>{formatMadridTime(slot.time)}</time>
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
          Hueco · conserva la última imagen
        </p>
        <p>← → para recorrer · pausa al cerrar el bucle</p>
      </footer>

      <p className="visually-hidden" aria-live="polite">
        {playbackAnnouncement}
      </p>
    </section>
  );
}

function radarAvailability(radar: RegionalRadarIndexEntry): RadarHealthStatus {
  return radar.available ? 'current' : 'no-data';
}

function statusLabel(status: RadarHealthStatus): string {
  return {
    current: 'Actualizado',
    delayed: 'Retrasado',
    'no-data': 'Sin datos',
    error: 'Error temporal',
  }[status];
}

function slotAnnouncement(
  slot: TimelineSlot,
  mapFrame: RadarTimelineFrame | null = null,
): string {
  const time = formatMadridTime(slot.time);
  if (slot.kind === 'frame') {
    return `Observación de las ${time}`;
  }
  const continuity = mapFrame
    ? ` Se mantiene la reflectividad de las ${formatMadridTime(mapFrame.time)}.`
    : '';
  return `Sin observación a las ${time}.${continuity}`;
}

function mostRecentFrame(
  slots: TimelineSlot[],
  selectedIndex: number,
): RadarTimelineFrame | null {
  for (let index = selectedIndex; index >= 0; index -= 1) {
    const slot = slots[index];
    if (slot?.kind === 'frame') {
      return slot.frame;
    }
  }
  return null;
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
