export const RADAR_INDEX_URL = '/radar/index.json';

export interface RegionalRadarIndexEntry {
  id: string;
  label: string;
  kind: 'regional';
  cadenceMinutes: number;
  manifestUrl: string;
  available: boolean;
  latestFrameTime: string | null;
  apiCode: string;
  siteCode: string;
  siteName: string;
  coordinates: [number, number];
  rangeKilometres: number;
  mapZoom: number;
  coverageRing: [number, number][];
  validation: {
    status: 'verified' | 'control-points' | 'awaiting-data';
    sampleVerified: boolean;
  };
}

export interface RadarIndex {
  schemaVersion: 1;
  generatedAt: string;
  radars: RegionalRadarIndexEntry[];
}

export function isRadarIndex(value: unknown): value is RadarIndex {
  if (!isRecord(value) || !Array.isArray(value.radars)) {
    return false;
  }
  const radars = value.radars;
  return (
    value.schemaVersion === 1 &&
    isDateTime(value.generatedAt) &&
    radars.length === 15 &&
    radars.every(isRegionalRadarIndexEntry) &&
    new Set(radars.map((radar) => radar.id)).size === radars.length
  );
}

function isRegionalRadarIndexEntry(
  value: unknown,
): value is RegionalRadarIndexEntry {
  if (!isRecord(value) || !isRecord(value.validation)) {
    return false;
  }
  const validation = value.validation;
  return (
    typeof value.id === 'string' &&
    value.id.startsWith('regional-') &&
    typeof value.label === 'string' &&
    value.kind === 'regional' &&
    isPositiveNumber(value.cadenceMinutes) &&
    typeof value.manifestUrl === 'string' &&
    value.manifestUrl.startsWith('/radar/') &&
    typeof value.available === 'boolean' &&
    (value.latestFrameTime === null || isDateTime(value.latestFrameTime)) &&
    typeof value.apiCode === 'string' &&
    typeof value.siteCode === 'string' &&
    typeof value.siteName === 'string' &&
    isCoordinate(value.coordinates) &&
    isPositiveNumber(value.rangeKilometres) &&
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
