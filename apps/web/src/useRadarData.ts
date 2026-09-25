import { useCallback, useEffect, useRef, useState } from 'react';
import { isRadarIndex, RADAR_INDEX_URL, type RadarIndex } from './radarIndex';
import {
  isRadarHealth,
  RADAR_HEALTH_URL,
  type RadarHealth,
} from './radarHealth';
import {
  buildTimelineSlots,
  isRadarManifest,
  type RadarManifest,
} from './radarManifest';
import { loadResilientJson, type DataSource } from './resilientData';
import { readStoredString, writeStoredValue } from './preferences';
const PREFERRED_RADAR_ID = 'regional-mu';
const SELECTED_RADAR_KEY = 'aemet-radar:selected-radar';
const CATALOG_CACHE_ID = 'catalog';
const HEALTH_CACHE_ID = 'health';
// Coincide con el intervalo de sondeo del worker.
export const AUTO_REFRESH_MILLISECONDS = 5 * 60 * 1000;

export function useRadarData() {
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
  const manifestRef = useRef<RadarManifest | null>(null);
  const selectedIndexRef = useRef(0);
  const [online, setOnline] = useState(() => navigator.onLine);
  const selectedRadar =
    index?.radars.find((radar) => radar.id === selectedRadarId) ?? null;
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
        if (controller.signal.aborted) return;
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
        if (controller.signal.aborted) return;
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
    if (selectedRadarId) {
      writeStoredValue(SELECTED_RADAR_KEY, selectedRadarId);
    }
  }, [selectedRadarId]);

  useEffect(() => {
    selectedIndexRef.current = selectedIndex;
  }, [selectedIndex]);

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

  const selectRadar = useCallback(
    (radarId: string) => {
      if (radarId === selectedRadarId) return;
      manifestRef.current = null;
      selectedIndexRef.current = 0;
      setManifest(null);
      setManifestError(false);
      setManifestSource('network');
      setSelectedIndex(0);
      setSelectedRadarId(radarId);
    },
    [selectedRadarId],
  );

  const selectIndex = useCallback(
    (value: number | ((current: number) => number)) => {
      const next =
        typeof value === 'function' ? value(selectedIndexRef.current) : value;
      selectedIndexRef.current = next;
      setSelectedIndex(next);
    },
    [],
  );
  const reload = useCallback(() => setReloadVersion((value) => value + 1), []);
  return {
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
    setSelectedIndex: selectIndex,
    online,
    selectRadar,
    reload,
  };
}
function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
