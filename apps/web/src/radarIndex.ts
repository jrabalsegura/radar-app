export const RADAR_INDEX_URL = '/radar/index.json';

interface BaseRadarIndexEntry {
  id: string;
  label: string;
  cadenceMinutes: number;
  manifestUrl: string;
  available: boolean;
  latestFrameTime: string | null;
  coordinates: [number, number];
  mapZoom: number;
  coverageRing: [number, number][];
  validation: {
    status: 'verified' | 'control-points' | 'awaiting-data';
    sampleVerified: boolean;
  };
}

export interface RegionalRadarIndexEntry extends BaseRadarIndexEntry {
  kind: 'regional';
  apiCode: string;
  siteCode: string;
  siteName: string;
  rangeKilometres: number;
  mapCenter?: [number, number];
}

export interface NationalRadarIndexEntry extends BaseRadarIndexEntry {
  id: 'national';
  kind: 'national';
  regionCode: 'PB';
  coverageLabel: string;
  includesCanaryIslands: false;
}

export type RadarIndexEntry = NationalRadarIndexEntry | RegionalRadarIndexEntry;

export interface RadarIndex {
  schemaVersion: 1;
  generatedAt: string;
  radars: RadarIndexEntry[];
}

export function isRadarIndex(value: unknown): value is RadarIndex {
  if (!isRecord(value) || !Array.isArray(value.radars)) {
    return false;
  }
  const radars = value.radars;
  return (
    value.schemaVersion === 1 &&
    isDateTime(value.generatedAt) &&
    radars.length === 16 &&
    radars.filter(isNationalRadarIndexEntry).length === 1 &&
    radars.filter(isRegionalRadarIndexEntry).length === 15 &&
    new Set(radars.map((radar) => radar.id)).size === radars.length
  );
}

function isBaseRadarIndexEntry(value: unknown): value is BaseRadarIndexEntry {
  if (!isRecord(value) || !isRecord(value.validation)) {
    return false;
  }
  const validation = value.validation;
  return (
    typeof value.id === 'string' &&
    typeof value.label === 'string' &&
    isPositiveNumber(value.cadenceMinutes) &&
    typeof value.manifestUrl === 'string' &&
    value.manifestUrl.startsWith('/radar/') &&
    typeof value.available === 'boolean' &&
    (value.latestFrameTime === null || isDateTime(value.latestFrameTime)) &&
    isCoordinate(value.coordinates) &&
    isPositiveNumber(value.mapZoom) &&
    Array.isArray(value.coverageRing) &&
    value.coverageRing.length >= 4 &&
    value.coverageRing.every(isCoordinate) &&
    (validation.status === 'verified' ||
      validation.status === 'control-points' ||
      validation.status === 'awaiting-data') &&
    typeof validation.sampleVerified === 'boolean'
  );
}

function isNationalRadarIndexEntry(
  value: unknown,
): value is NationalRadarIndexEntry {
  return (
    isBaseRadarIndexEntry(value) &&
    isRecord(value) &&
    value.id === 'national' &&
    value.kind === 'national' &&
    value.regionCode === 'PB' &&
    typeof value.coverageLabel === 'string' &&
    value.includesCanaryIslands === false
  );
}

function isRegionalRadarIndexEntry(
  value: unknown,
): value is RegionalRadarIndexEntry {
  return (
    isBaseRadarIndexEntry(value) &&
    isRecord(value) &&
    value.id.startsWith('regional-') &&
    value.kind === 'regional' &&
    typeof value.apiCode === 'string' &&
    typeof value.siteCode === 'string' &&
    typeof value.siteName === 'string' &&
    (value.mapCenter === undefined || isCoordinate(value.mapCenter)) &&
    isPositiveNumber(value.rangeKilometres)
  );
}

function isCoordinate(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    value.every(
      (component) =>
        typeof component === 'number' && Number.isFinite(component),
    )
  );
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function isDateTime(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
