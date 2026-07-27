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
import { preloadInPriorityOrder } from './framePreloader';
import { recordAppReady } from './performanceMetrics';
import type { RadarCameraInsets } from './radarCamera';
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
  type RadarIndexEntry,
} from './radarIndex';
import { closestRegionalRadar, type LongitudeLatitude } from './radarLocation';
import {
  buildTimelineSlots,
  formatMadridDate,
  formatMadridTime,
  formatMadridTimeZoneName,
  HISTORY_LABEL,
  isRadarManifest,
  type RadarManifest,
  type RadarTimelineFrame,
  type TimelineSlot,
} from './radarManifest';
import { loadResilientJson, type DataSource } from './resilientData';

const SPEEDS = {
  slow: { label: 'Lenta', milliseconds: 1500 },
  normal: { label: 'Normal', milliseconds: 850 },
  fast: { label: 'Rápida', milliseconds: 420 },
} as const;
const LAST_FRAME_PAUSE_FACTOR = 2.4;
const PREFERRED_RADAR_ID = 'regional-mu';
const SELECTED_RADAR_KEY = 'aemet-radar:selected-radar';
const OPACITY_KEY = 'aemet-radar:opacity';
const CATALOG_CACHE_ID = 'catalog';
const HEALTH_CACHE_ID = 'health';
const AUTO_REFRESH_MILLISECONDS = 10 * 60 * 1000;

type PlaybackSpeed = keyof typeof SPEEDS;
type LocationStatus = 'idle' | 'locating' | 'located' | 'error';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const LazyRadarMap = lazy(async () => {
  const module = await import('./RadarMap');
  return { default: module.RadarMap };
});

export function App() {
  const [index, setIndex] = useState<RadarIndex | null>(null);
  const [health, setHealth] = useState<RadarHealth | null>(null);
  const [selectedRadarId, setSelectedRadarId] = useState('');
  const [manifest, setManifest] = useState<RadarManifest | null>(null);
  const [catalogError, setCatalogError] = useState(false);
  const [manifestError, setManifestError] = useState(false);
  const [catalogSource, setCatalogSource] = useState<DataSource>('network');
  const [manifestSource, setManifestSource] = useState<DataSource>('network');
  const [reloadVersion, setReloadVersion] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>('normal');
  const [opacity, setOpacity] = useState(() =>
    readStoredNumber(OPACITY_KEY, 0.72, 0, 1),
  );
  const [showDebug, setShowDebug] = useState(false);
  const [online, setOnline] = useState(() => navigator.onLine);
  const [locationStatus, setLocationStatus] = useState<LocationStatus>('idle');
  const [locationMessage, setLocationMessage] = useState('');
  const [userCoordinates, setUserCoordinates] =
    useState<LongitudeLatitude | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [installPrompt, setInstallPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const selectedButtonRef = useRef<HTMLButtonElement | null>(null);
  const mapLayoutRef = useRef<HTMLElement | null>(null);
  const mapTopOverlayRef = useRef<HTMLDivElement | null>(null);
  const timelinePanelRef = useRef<HTMLElement | null>(null);
  const manifestRef = useRef<RadarManifest | null>(null);
  const selectedIndexRef = useRef(0);
  const [mapInsets, setMapInsets] = useState<RadarCameraInsets>({
    top: 0,
    bottom: 0,
  });
  const reducedMotion = useReducedMotion();
  const now = useMinuteClock();
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
      setCatalogError(false);
      try {
        const [indexResult, healthResult] = await Promise.all([
          loadResilientJson(
            RADAR_INDEX_URL,
            CATALOG_CACHE_ID,
            isRadarIndex,
            controller.signal,
          ),
          loadResilientJson(
            RADAR_HEALTH_URL,
            HEALTH_CACHE_ID,
            isRadarHealth,
            controller.signal,
          ).catch(() => null),
        ]);
        setIndex(indexResult.data);
        setHealth(healthResult?.data ?? null);
        setCatalogSource(
          indexResult.source === 'cache' || healthResult?.source === 'cache'
            ? 'cache'
            : 'network',
        );
        const storedRadarId = readStoredString(SELECTED_RADAR_KEY);
        const preferred =
          indexResult.data.radars.find((radar) => radar.id === storedRadarId) ??
          indexResult.data.radars.find(
            (radar) => radar.id === PREFERRED_RADAR_ID,
          );
        setSelectedRadarId(
          (current) =>
            indexResult.data.radars.find((radar) => radar.id === current)?.id ??
            preferred?.id ??
            indexResult.data.radars[0]?.id ??
            '',
        );
      } catch (error) {
        if (!isAbortError(error)) {
          setCatalogError(true);
        }
      }
    }

    void loadCatalog();
    return () => controller.abort();
  }, [reloadVersion]);

  const manifestRadarId = selectedRadar?.id;
  const selectedManifestUrl = selectedRadar?.manifestUrl;

  useEffect(() => {
    if (!manifestRadarId || !selectedManifestUrl) {
      return;
    }
    const controller = new AbortController();
    const radarId = manifestRadarId;
    const manifestUrl = selectedManifestUrl;

    async function loadManifest() {
      setManifestError(false);
      try {
        const result = await loadResilientJson(
          manifestUrl,
          `manifest:${radarId}`,
          (value): value is RadarManifest =>
            isRadarManifest(value) && value.radar.id === radarId,
          controller.signal,
        );
        const previousSlots = manifestRef.current
          ? buildTimelineSlots(manifestRef.current)
          : [];
        const currentIndex = selectedIndexRef.current;
        const selectedTime = previousSlots[currentIndex]?.time;
        const wasFollowingLatest =
          previousSlots.length === 0 ||
          currentIndex >= previousSlots.length - 1;
        const nextSlots = buildTimelineSlots(result.data);
        const matchingIndex = selectedTime
          ? nextSlots.findIndex((slot) => slot.time === selectedTime)
          : -1;
        const nextIndex = wasFollowingLatest
          ? Math.max(0, nextSlots.length - 1)
          : matchingIndex >= 0
            ? matchingIndex
            : Math.min(currentIndex, Math.max(0, nextSlots.length - 1));
        manifestRef.current = result.data;
        selectedIndexRef.current = nextIndex;
        setManifest(result.data);
        setManifestSource(result.source);
        setSelectedIndex(nextIndex);
      } catch (error) {
        if (!isAbortError(error)) {
          setManifestError(true);
        }
      }
    }

    void loadManifest();
    return () => controller.abort();
  }, [manifestRadarId, reloadVersion, selectedManifestUrl]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setReloadVersion((current) => current + 1);
    }, AUTO_REFRESH_MILLISECONDS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    writeStoredValue(OPACITY_KEY, String(opacity));
  }, [opacity]);

  useEffect(() => {
    if (selectedRadarId) {
      writeStoredValue(SELECTED_RADAR_KEY, selectedRadarId);
    }
  }, [selectedRadarId]);

  useEffect(() => {
    selectedIndexRef.current = selectedIndex;
  }, [selectedIndex]);

  useEffect(() => {
    const layout = mapLayoutRef.current;
    const topOverlay = mapTopOverlayRef.current;
    const panel = timelinePanelRef.current;
    if (!layout) {
      return;
    }
    const layoutElement = layout;
    const topOverlayElement = topOverlay;
    const panelElement = panel;

    function measureOverlays() {
      const layoutRect = layoutElement.getBoundingClientRect();
      const topOffset = topOverlayElement
        ? Number.parseFloat(window.getComputedStyle(topOverlayElement).top)
        : 0;
      const bottomOffset = panelElement
        ? Number.parseFloat(window.getComputedStyle(panelElement).bottom)
        : 0;
      const top = topOverlayElement
        ? Math.ceil(
            topOverlayElement.getBoundingClientRect().bottom -
              layoutRect.top +
              (Number.isFinite(topOffset) ? topOffset : 0),
          )
        : 0;
      const bottom = panelElement
        ? Math.ceil(
            layoutRect.bottom -
              panelElement.getBoundingClientRect().top +
              (Number.isFinite(bottomOffset) ? bottomOffset : 0),
          )
        : 0;
      setMapInsets((current) =>
        current.top === top && current.bottom === bottom
          ? current
          : { top, bottom },
      );
    }

    measureOverlays();
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(measureOverlays);
    observer?.observe(layoutElement);
    if (topOverlayElement) {
      observer?.observe(topOverlayElement);
    }
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
    function updateConnection() {
      const connected = navigator.onLine;
      setOnline(connected);
      if (connected) {
        setReloadVersion((current) => current + 1);
      }
    }
    window.addEventListener('online', updateConnection);
    window.addEventListener('offline', updateConnection);
    return () => {
      window.removeEventListener('online', updateConnection);
      window.removeEventListener('offline', updateConnection);
    };
  }, []);

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

  const selectRadar = useCallback((radarId: string) => {
    manifestRef.current = null;
    selectedIndexRef.current = 0;
    setManifest(null);
    setManifestError(false);
    setManifestSource('network');
    setPlaying(false);
    setLocationStatus('idle');
    setLocationMessage('');
    setSelectedIndex(0);
    setSelectedRadarId(radarId);
  }, []);

  function locateNearestRadar() {
    if (!index || !('geolocation' in navigator)) {
      setLocationStatus('error');
      setLocationMessage('La geolocalización no está disponible.');
      return;
    }
    setLocationStatus('locating');
    setLocationMessage('Buscando el radar más cercano…');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coordinates: LongitudeLatitude = [
          position.coords.longitude,
          position.coords.latitude,
        ];
        const nearest = closestRegionalRadar(index.radars, coordinates);
        if (!nearest) {
          setLocationStatus('error');
          setLocationMessage('No hay radares regionales configurados.');
          return;
        }
        setUserCoordinates(coordinates);
        selectRadar(nearest.id);
        setLocationStatus('located');
        setLocationMessage(`Radar más cercano: ${nearest.label}.`);
      },
      () => {
        setLocationStatus('error');
        setLocationMessage(
          'No se pudo obtener tu ubicación. Puedes elegir el radar manualmente.',
        );
      },
      {
        enableHighAccuracy: false,
        maximumAge: 10 * 60 * 1000,
        timeout: 10_000,
      },
    );
  }

  async function toggleFullscreen() {
    const target = mapLayoutRef.current;
    if (!target || !document.fullscreenEnabled) {
      return;
    }
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
              onClick={() => setReloadVersion((current) => current + 1)}
            >
              Reintentar
            </button>
          )}
        </div>
      </main>
    );
  }

  const selectedFrame =
    selectedSlot?.kind === 'frame' ? selectedSlot.frame : null;
  const mapFrame = selectedSlot ? mostRecentFrame(slots, selectedIndex) : null;
  const baseStatus = selectedHealth?.status ?? radarAvailability(selectedRadar);
  const status: RadarHealthStatus = manifestError
    ? 'error'
    : manifestSource === 'cache' && baseStatus === 'current'
      ? 'delayed'
      : baseStatus;
  const freshness = manifest?.latestFrameTime
    ? `Último dato ${formatMadridTime(manifest.latestFrameTime)} · ${formatDataAge(manifest.latestFrameTime, now)}`
    : 'Sin dato publicado';
  const showingCachedData =
    catalogSource === 'cache' || manifestSource === 'cache';

  function selectSlot(indexValue: number) {
    selectedIndexRef.current = indexValue;
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
                      {radar.label}
                      {radar.available ? '' : ' · sin datos'}
                    </option>
                  ))}
              </optgroup>
              <optgroup label="Radares regionales">
                {index.radars
                  .filter((radar) => radar.kind === 'regional')
                  .map((radar) => (
                    <option key={radar.id} value={radar.id}>
                      {radar.label}
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
            opacity={opacity}
            showDebug={showDebug}
            reducedMotion={reducedMotion}
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

        {selectedSlot && manifest ? (
          <FrameCard
            manifest={manifest}
            selectedSlot={selectedSlot}
            selectedFrame={selectedFrame}
            mapFrame={mapFrame}
            now={now}
            cardRef={mapTopOverlayRef}
          />
        ) : (
          <div
            ref={mapTopOverlayRef}
            className={`no-data-card${manifestError ? ' no-data-card--error' : ''}`}
            role={manifestError ? 'alert' : 'status'}
          >
            <p className="frame-card__label">
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
                onClick={() => setReloadVersion((current) => current + 1)}
              >
                Reintentar
              </button>
            )}
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
              fullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'
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

        {selectedSlot && manifest && (
          <Timeline
            manifest={manifest}
            slots={slots}
            selectedIndex={selectedIndex}
            selectedSlot={selectedSlot}
            mapFrame={mapFrame}
            playing={playing}
            speed={speed}
            panelRef={timelinePanelRef}
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
  now: number;
  cardRef: RefObject<HTMLDivElement | null>;
}

function FrameCard({
  manifest,
  selectedSlot,
  selectedFrame,
  mapFrame,
  now,
  cardRef,
}: FrameCardProps) {
  const isLatest =
    selectedSlot.kind === 'frame' &&
    selectedSlot.time === manifest.latestFrameTime;
  return (
    <div
      ref={cardRef}
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
        {formatMadridDate(selectedSlot.time)} · hora de Madrid (
        {formatMadridTimeZoneName(selectedSlot.time)})
        {selectedFrame?.timeSource === 'retrievedAt'
          ? ' · producto sin hora verificable'
          : ''}
      </p>
      <p className="frame-card__age">
        Antigüedad: {formatDataAge(selectedSlot.time, now)}
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
  panelRef: RefObject<HTMLElement | null>;
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
  panelRef,
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

function radarAvailability(radar: RadarIndexEntry): RadarHealthStatus {
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

function useMinuteClock(): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return now;
}

function readStoredString(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function readStoredNumber(
  key: string,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const stored = readStoredString(key);
  if (stored === null) {
    return fallback;
  }
  const value = Number(stored);
  return Number.isFinite(value) && value >= minimum && value <= maximum
    ? value
    : fallback;
}

function writeStoredValue(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Las preferencias son opcionales en contextos con almacenamiento bloqueado.
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
