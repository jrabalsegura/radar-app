import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from 'react';

import { formatDataAge } from './dataFreshness';
import { radarStatus } from './radarStatus';
import { DbzLegend } from './DbzLegend';
import { recordAppReady } from './performanceMetrics';
import type { RadarCameraInsets } from './radarCamera';
import type { RadarHealthStatus } from './radarHealth';
import { radarIdForHotkey, radarLabelWithHotkey } from './radarHotkeys';
import {
  buildTimelineSlots,
  formatMadridTime,
  formatMadridDate,
  formatMadridTimeZoneName,
  HISTORY_LABEL,
  type RadarManifest,
  type RadarTimelineFrame,
  type TimelineSlot,
} from './radarManifest';
import { useRadarData } from './useRadarData';
import { useRadarLocation } from './useRadarLocation';
import { readStoredNumber, writeStoredValue } from './preferences';

const SPEEDS = {
  slow: { label: 'Lenta', milliseconds: 1500 },
  normal: { label: 'Normal', milliseconds: 850 },
  fast: { label: 'Rápida', milliseconds: 420 },
} as const;
const LAST_FRAME_PAUSE_FACTOR = 2.4;
const OPACITY_KEY = 'aemet-radar:opacity';
const NO_FRAMES: readonly RadarTimelineFrame[] = [];

type PlaybackSpeed = keyof typeof SPEEDS;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const LazyRadarMap = lazy(async () => {
  const module = await import('./RadarMap');
  return { default: module.RadarMap };
});

export function App() {
  const {
    index,
    health,
    selectedRadarId,
    selectedRadar,
    manifest,
    catalogError,
    manifestError,
    catalogSource,
    manifestSource,
    selectedIndex,
    setSelectedIndex,
    online,
    selectRadar: selectRadarData,
    reload,
  } = useRadarData();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>('normal');
  const [opacity, setOpacity] = useState(() =>
    readStoredNumber(OPACITY_KEY, 0.72, 0, 1),
  );
  const [showDebug, setShowDebug] = useState(false);
  const [showNoCoverage, setShowNoCoverage] = useState(false);
  const [recenterRequest, setRecenterRequest] = useState(0);
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const [displayedImage, setDisplayedImage] = useState<{
    radarId: string;
    frame: RadarTimelineFrame | null;
  } | null>(null);
  const onDisplayedFrame = useCallback(
    (frame: RadarTimelineFrame | null) => {
      setDisplayedImage({ radarId: selectedRadarId, frame });
      setFailedImage(null);
    },
    [selectedRadarId],
  );
  const [fullscreen, setFullscreen] = useState(false);
  const [mapMenuOpen, setMapMenuOpen] = useState(false);
  const [installPrompt, setInstallPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const selectedButtonRef = useRef<HTMLButtonElement | null>(null);
  const timelineSliderRef = useRef<HTMLInputElement | null>(null);
  const focusedTimelineRadarRef = useRef<string | null>(null);
  const mapLayoutRef = useRef<HTMLElement | null>(null);
  const mapMenuRef = useRef<HTMLDivElement | null>(null);
  const mapMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const timelinePanelRef = useRef<HTMLElement | null>(null);
  const [mapInsets, setMapInsets] = useState<RadarCameraInsets>({
    top: 0,
    bottom: 0,
  });
  const reducedMotion = useReducedMotion();
  const now = useMinuteClock();
  const chooseRadar = useCallback(
    (radarId: string) => {
      if (radarId === selectedRadarId) return;
      selectRadarData(radarId);
      setPlaying(false);
      setMapMenuOpen(false);
    },
    [selectRadarData, selectedRadarId],
  );
  const {
    locationStatus,
    locationMessage,
    userCoordinates,
    locateNearestRadar,
    resetLocation,
  } = useRadarLocation(index, chooseRadar);
  const selectRadar = useCallback(
    (radarId: string) => {
      resetLocation();
      chooseRadar(radarId);
    },
    [chooseRadar, resetLocation],
  );
  const slots = useMemo(
    () => (manifest ? buildTimelineSlots(manifest) : []),
    [manifest],
  );
  const selectedSlot = slots[selectedIndex] ?? null;

  useEffect(() => {
    writeStoredValue(OPACITY_KEY, String(opacity));
  }, [opacity]);

  useEffect(() => {
    const layout = mapLayoutRef.current;
    const panel = timelinePanelRef.current;
    if (!layout) {
      return;
    }
    const layoutElement = layout;
    const panelElement = panel;

    function measureOverlays() {
      const layoutRect = layoutElement.getBoundingClientRect();
      const bottomOffset = panelElement
        ? Number.parseFloat(window.getComputedStyle(panelElement).bottom)
        : 0;
      const bottom = panelElement
        ? Math.ceil(
            layoutRect.bottom -
              panelElement.getBoundingClientRect().top +
              (Number.isFinite(bottomOffset) ? bottomOffset : 0),
          )
        : 0;
      setMapInsets((current) =>
        current.top === 0 && current.bottom === bottom
          ? current
          : { top: 0, bottom },
      );
    }

    measureOverlays();
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(measureOverlays);
    observer?.observe(layoutElement);
    if (panelElement) {
      observer?.observe(panelElement);
    }
    window.addEventListener('resize', measureOverlays);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', measureOverlays);
    };
  }, [fullscreen, manifest, manifestError, selectedRadarId]);

  useEffect(() => {
    if (!mapMenuOpen) {
      return;
    }

    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !mapMenuRef.current?.contains(target)) {
        setMapMenuOpen(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== 'Escape') {
        return;
      }
      setMapMenuOpen(false);
      mapMenuButtonRef.current?.focus();
    }

    document.addEventListener('pointerdown', closeOnOutsidePointer);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [mapMenuOpen]);

  useEffect(() => {
    function updateFullscreen() {
      setFullscreen(document.fullscreenElement === mapLayoutRef.current);
    }
    function captureInstallPrompt(event: Event) {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    }
    document.addEventListener('fullscreenchange', updateFullscreen);
    window.addEventListener('beforeinstallprompt', captureInstallPrompt);
    return () => {
      document.removeEventListener('fullscreenchange', updateFullscreen);
      window.removeEventListener('beforeinstallprompt', captureInstallPrompt);
    };
  }, []);

  useEffect(() => {
    if (
      !manifest ||
      manifest.radar.id !== selectedRadarId ||
      focusedTimelineRadarRef.current === selectedRadarId ||
      slots.length === 0
    ) {
      return;
    }
    const slider = timelineSliderRef.current;
    if (!slider) {
      return;
    }
    focusedTimelineRadarRef.current = selectedRadarId;
    slider.focus({ preventScroll: true });
  }, [manifest, selectedRadarId, slots.length]);

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
  }, [playing, selectedIndex, slots.length, speed, setSelectedIndex]);

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
  }, [slots.length, setSelectedIndex]);

  useEffect(() => {
    function pauseWhenHidden() {
      if (document.hidden) {
        setPlaying(false);
      }
    }
    document.addEventListener('visibilitychange', pauseWhenHidden);
    return () =>
      document.removeEventListener('visibilitychange', pauseWhenHidden);
  }, []);

  useEffect(() => {
    if (manifest) {
      recordAppReady();
    }
  }, [manifest]);

  useEffect(() => {
    if (!index) {
      return;
    }
    const availableRadarIds = new Set(index.radars.map((radar) => radar.id));

    function selectRadarWithHotkey(event: KeyboardEvent) {
      if (
        event.defaultPrevented ||
        event.repeat ||
        event.isComposing ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        shouldIgnoreRadarHotkeyTarget(event.target)
      ) {
        return;
      }
      const radarId = radarIdForHotkey(event.key);
      if (
        !radarId ||
        radarId === selectedRadarId ||
        !availableRadarIds.has(radarId)
      ) {
        return;
      }
      event.preventDefault();
      selectRadar(radarId);
    }

    document.addEventListener('keydown', selectRadarWithHotkey);
    return () => document.removeEventListener('keydown', selectRadarWithHotkey);
  }, [index, selectRadar, selectedRadarId]);

  async function toggleFullscreen() {
    const target = mapLayoutRef.current;
    if (!target || !document.fullscreenEnabled) {
      return;
    }
    setMapMenuOpen(false);
    if (document.fullscreenElement === target) {
      await document.exitFullscreen();
    } else {
      await target.requestFullscreen();
    }
  }

  async function installApplication() {
    if (!installPrompt) {
      return;
    }
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  }

  if (!index || !selectedRadar) {
    return (
      <main className="radar-app radar-app--initial">
        <div className="initial-state" role={catalogError ? 'alert' : 'status'}>
          <p className="eyebrow">Red radar AEMET</p>
          <h1>
            {catalogError
              ? 'No se pudo abrir el catálogo'
              : 'Preparando las fuentes de radar…'}
          </h1>
          <p>
            {catalogError
              ? 'No hay una copia válida guardada. Comprueba la conexión y vuelve a intentarlo.'
              : 'Cargando la composición nacional y los 15 emplazamientos regionales.'}
          </p>
          {catalogError && (
            <button
              className="retry-button"
              type="button"
              onClick={() => reload()}
            >
              Reintentar
            </button>
          )}
        </div>
      </main>
    );
  }

  const mapFrame = selectedSlot ? mostRecentFrame(slots, selectedIndex) : null;
  const status = radarStatus(
    selectedRadar,
    manifest,
    health,
    now,
    catalogSource === 'cache' || manifestSource === 'cache' || !online,
    manifestError,
  );
  const displayedFrame =
    displayedImage?.radarId === selectedRadarId ? displayedImage.frame : null;
  const freshness = manifest?.latestFrameTime
    ? `Último dato ${formatMadridTime(manifest.latestFrameTime)} · ${formatDataAge(manifest.latestFrameTime, now)}`
    : 'Sin dato publicado';
  const showingCachedData =
    catalogSource === 'cache' || manifestSource === 'cache';

  function selectSlot(indexValue: number) {
    setPlaying(false);
    setSelectedIndex(indexValue);
  }

  return (
    <main className="radar-app">
      <header className="topbar">
        <div className="radar-heading">
          <p className="eyebrow">Últimas {HISTORY_LABEL}</p>
          <h1>
            {selectedRadar.kind === 'national'
              ? selectedRadar.label
              : `Radar ${selectedRadar.label}`}
          </h1>
          <div className="radar-status-line" role="status" aria-live="polite">
            <span className={`status-chip status-chip--${status}`}>
              {statusLabel(status)}
            </span>
            <span className="data-freshness">{freshness}</span>
          </div>
        </div>

        <div className="radar-selector">
          <label htmlFor="radar-source">Fuente radar</label>
          <div className="radar-selector__row">
            <select
              id="radar-source"
              value={selectedRadar.id}
              onChange={(event) => selectRadar(event.currentTarget.value)}
            >
              <optgroup label="Composición nacional">
                {index.radars
                  .filter((radar) => radar.kind === 'national')
                  .map((radar) => (
                    <option key={radar.id} value={radar.id}>
                      {radarLabelWithHotkey(radar.id, radar.label)}
                      {radar.available ? '' : ' · sin datos'}
                    </option>
                  ))}
              </optgroup>
              <optgroup label="Radares regionales">
                {index.radars
                  .filter((radar) => radar.kind === 'regional')
                  .map((radar) => (
                    <option key={radar.id} value={radar.id}>
                      {radarLabelWithHotkey(radar.id, radar.label)}
                      {radar.available ? '' : ' · sin datos'}
                    </option>
                  ))}
              </optgroup>
            </select>
            <button
              className="location-button"
              type="button"
              disabled={locationStatus === 'locating'}
              aria-label="Usar mi ubicación para elegir el radar más cercano"
              title="La ubicación se procesa solo en este dispositivo"
              onClick={locateNearestRadar}
            >
              {locationStatus === 'locating' ? 'Localizando…' : 'Cerca de mí'}
            </button>
            <button
              className="national-button"
              type="button"
              aria-label="Ir a composición nacional"
              aria-pressed={selectedRadar.id === 'national'}
              onClick={() => selectRadar('national')}
            >
              Nacional
            </button>
          </div>
          <span aria-live="polite">
            {locationMessage ||
              (selectedRadar.kind === 'national'
                ? `${selectedRadar.coverageLabel} · Canarias usa el radar regional de Las Palmas`
                : selectedRadar.siteName)}
          </span>
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
          {installPrompt && (
            <button
              className="install-button"
              type="button"
              onClick={() => void installApplication()}
            >
              Instalar
            </button>
          )}
        </div>
      </header>

      <section
        ref={mapLayoutRef}
        className="map-layout"
        aria-label={`Reproductor de ${selectedRadar.label}`}
      >
        <Suspense
          fallback={
            <p className="map-loading" role="status">
              Preparando cartografía…
            </p>
          }
        >
          <LazyRadarMap
            key={selectedRadar.id}
            radar={selectedRadar}
            selectedFrame={mapFrame}
            frames={manifest?.frames ?? NO_FRAMES}
            opacity={opacity}
            showDebug={showDebug}
            showNoCoverage={showNoCoverage}
            recenterRequest={recenterRequest}
            onDisplayedFrame={onDisplayedFrame}
            onFailedImage={setFailedImage}
            userCoordinates={userCoordinates}
            cameraInsets={mapInsets}
          />
        </Suspense>

        {(!online || showingCachedData) && (
          <p className="connection-banner" role="status">
            {!online ? 'Sin conexión' : 'Conexión inestable'} · mostrando la
            última copia válida guardada
          </p>
        )}

        {!selectedSlot || !manifest ? (
          <div
            className={`no-data-card${manifestError ? ' no-data-card--error' : ''}`}
            role={manifestError ? 'alert' : 'status'}
          >
            <p className="no-data-card__label">
              {selectedRadar.kind === 'national'
                ? selectedRadar.regionCode
                : selectedRadar.siteCode}
            </p>
            <h2>
              {manifestError
                ? 'No se pudo abrir este historial'
                : manifest
                  ? 'Sin imágenes disponibles ahora'
                  : 'Cargando historial…'}
            </h2>
            <p>
              {manifestError
                ? 'No hay una copia válida guardada para esta fuente. Puedes reintentar o seleccionar otra.'
                : manifest
                  ? 'Esta fuente permanece configurada y seguirá consultándose. Las imágenes aparecerán automáticamente cuando AEMET vuelva a publicarlas.'
                  : 'El mapa ya está centrado en la fuente seleccionada.'}
            </p>
            {manifestError && (
              <button
                className="retry-button"
                type="button"
                onClick={() => reload()}
              >
                Reintentar
              </button>
            )}
          </div>
        ) : null}

        <div className="map-quick-actions">
          <button
            type="button"
            onClick={() => setRecenterRequest((value) => value + 1)}
          >
            Centrar radar
          </button>
          <DbzLegend />
        </div>
        <div ref={mapMenuRef} className="map-options">
          <button
            ref={mapMenuButtonRef}
            className="map-options__trigger"
            type="button"
            aria-label={
              mapMenuOpen
                ? 'Cerrar opciones del mapa'
                : 'Abrir opciones del mapa'
            }
            aria-expanded={mapMenuOpen}
            aria-controls="map-options-panel"
            onClick={() => setMapMenuOpen((open) => !open)}
          >
            <span className="map-options__icon" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </button>
          {mapMenuOpen && (
            <div
              id="map-options-panel"
              className="map-options__panel"
              role="group"
              aria-label="Controles del mapa"
            >
              <p className="map-options__title">Opciones del mapa</p>
              <label className="map-options__opacity">
                <span>Opacidad del radar</span>
                <span className="map-options__range">
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
                </span>
              </label>
              <button
                className="no-coverage-button"
                type="button"
                aria-pressed={showNoCoverage}
                onClick={() => setShowNoCoverage((visible) => !visible)}
              >
                {showNoCoverage
                  ? 'Ocultar zonas sin cobertura'
                  : 'Ver zonas sin cobertura'}
              </button>
              <div className="map-options__actions">
                <button
                  className="coverage-button"
                  type="button"
                  aria-pressed={showDebug}
                  onClick={() => setShowDebug((visible) => !visible)}
                >
                  {showDebug ? 'Ocultar cobertura' : 'Ver cobertura'}
                </button>
                <button
                  className="fullscreen-button"
                  type="button"
                  aria-label={
                    fullscreen
                      ? 'Salir de pantalla completa'
                      : 'Pantalla completa'
                  }
                  aria-pressed={fullscreen}
                  disabled={!document.fullscreenEnabled}
                  title={
                    document.fullscreenEnabled
                      ? undefined
                      : 'Pantalla completa no disponible en este navegador'
                  }
                  onClick={() => void toggleFullscreen()}
                >
                  {fullscreen ? 'Salir' : 'Ampliar'}
                </button>
              </div>
            </div>
          )}
        </div>

        {selectedSlot && manifest && (
          <Timeline
            manifest={manifest}
            slots={slots}
            selectedIndex={selectedIndex}
            selectedSlot={selectedSlot}
            mapFrame={displayedFrame}
            requestedFrame={mapFrame}
            failedImage={failedImage}
            playing={playing}
            speed={speed}
            panelRef={timelinePanelRef}
            sliderRef={timelineSliderRef}
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

interface TimelineProps {
  manifest: RadarManifest;
  slots: TimelineSlot[];
  selectedIndex: number;
  selectedSlot: TimelineSlot;
  mapFrame: RadarTimelineFrame | null;
  requestedFrame: RadarTimelineFrame | null;
  failedImage: string | null;
  playing: boolean;
  speed: PlaybackSpeed;
  panelRef: RefObject<HTMLElement | null>;
  sliderRef: RefObject<HTMLInputElement | null>;
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
  requestedFrame,
  failedImage,
  playing,
  speed,
  panelRef,
  sliderRef,
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
    <section
      ref={panelRef}
      className="timeline-panel"
      aria-label="Controles temporales"
    >
      <div className="timeline-current">
        <p data-testid="visible-frame-time">
          {mapFrame ? (
            <>
              <strong>
                {mapFrame.timeSource === 'retrievedAt' ? 'Obtenida' : 'Imagen'}:{' '}
                {formatMadridTime(mapFrame.time)}
              </strong>
              <span>
                {' '}
                · {formatMadridDate(mapFrame.time)} ·{' '}
                {formatMadridTimeZoneName(mapFrame.time)}
              </span>
              {mapFrame.timeSource === 'retrievedAt' && (
                <span> · hora del producto desconocida</span>
              )}
              {(mapFrame.sourceProvider === 'aemet-opendata' ||
                (!mapFrame.sourceProvider &&
                  mapFrame.rawUrl.endsWith('.gif'))) && (
                <span> · fuente alternativa</span>
              )}
            </>
          ) : (
            <strong>Sin imagen visible</strong>
          )}
          {selectedSlot.kind === 'gap' && (
            <span className="timeline-current__gap">
              {' '}
              · {formatMadridTime(selectedSlot.time)}: intervalo sin dato
            </span>
          )}
          {requestedFrame && requestedFrame.imageUrl !== mapFrame?.imageUrl && (
            <span>
              {' '}
              ·{' '}
              {failedImage === requestedFrame.imageUrl
                ? 'no se pudo cargar'
                : 'cargando'}{' '}
              {formatMadridTime(requestedFrame.time)}
            </span>
          )}
        </p>
        <button type="button" onClick={() => onSelect(slots.length - 1)}>
          Ir a la última
        </button>
      </div>
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
            ref={sliderRef}
            aria-label="Instante del radar"
            aria-valuetext={slotAnnouncement(selectedSlot, mapFrame)}
            type="range"
            min="0"
            max={slots.length - 1}
            step="1"
            value={selectedIndex}
            onKeyDown={(event) => {
              if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
                return;
              }
              event.preventDefault();
              const direction = event.key === 'ArrowLeft' ? -1 : 1;
              onSelect(
                Math.min(
                  slots.length - 1,
                  Math.max(0, selectedIndex + direction),
                ),
              );
            }}
            onChange={(event) => onSelect(Number(event.currentTarget.value))}
          />
          <span className="timeline-range">
            <time dateTime={firstSlot.time}>
              {formatMadridTime(firstSlot.time)}
            </time>
            <span>{HISTORY_LABEL}</span>
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
              {latest && <small>Última</small>}
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

function shouldIgnoreRadarHotkeyTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target.isContentEditable ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLInputElement && target.type !== 'range')
  );
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

function useMinuteClock(): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return now;
}
