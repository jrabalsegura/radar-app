export const HISTORY_MINUTES = 230;
export const HISTORY_HOURS = HISTORY_MINUTES / 60;
export const HISTORY_LABEL = '3 h 50 min';
export const MADRID_TIME_ZONE = 'Europe/Madrid';

export type MapCoordinates = [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
];

export interface RadarTimelineFrame {
  id: string;
  time: string;
  timeSource: 'productTime' | 'retrievedAt';
  productTime: string | null;
  retrievedAt: string;
  lastRetrievedAt: string;
  sourceHash: string;
  rawUrl: string;
  imageUrl: string;
  imageCoordinates: MapCoordinates;
  status: 'available';
}

export interface RadarTimelineGap {
  after: string | null;
  before: string;
  expectedCadenceMinutes: number;
  missingCount: number;
  expectedTimes: string[];
  timeBasis: 'productTime' | 'retrievedAt' | 'mixed';
}

export interface RadarManifest {
  schemaVersion: 1;
  radar: {
    id: string;
    label: string;
    kind: 'regional';
    cadenceMinutes: number;
  };
  generatedAt: string;
  window: {
    hours: number;
    minutes: 230;
    start: string | null;
    end: string | null;
    anchor: 'latest-available-frame';
  };
  latestFrameTime: string | null;
  latestProductTime: string | null;
  timeBasis: 'productTime' | 'retrievedAt' | 'mixed' | null;
  frames: RadarTimelineFrame[];
  gaps: RadarTimelineGap[];
  statistics: {
    archivedFrames: number;
    publishedFrames: number;
    discardedDuplicates: number;
    invalidReports: number;
  };
}

export type TimelineSlot =
  | {
      kind: 'frame';
      id: string;
      time: string;
      frame: RadarTimelineFrame;
    }
  | {
      kind: 'gap';
      id: string;
      time: string;
      gap: RadarTimelineGap;
    };

export function isRadarManifest(value: unknown): value is RadarManifest {
  if (!isRecord(value)) {
    return false;
  }
  const radar = value.radar;
  const window = value.window;
  const statistics = value.statistics;
  if (
    value.schemaVersion !== 1 ||
    !isRecord(radar) ||
    typeof radar.id !== 'string' ||
    !radar.id.startsWith('regional-') ||
    typeof radar.label !== 'string' ||
    radar.kind !== 'regional' ||
    !isPositiveNumber(radar.cadenceMinutes) ||
    !isDateTime(value.generatedAt) ||
    !isRecord(window) ||
    window.hours !== HISTORY_HOURS ||
    window.minutes !== HISTORY_MINUTES ||
    window.anchor !== 'latest-available-frame' ||
    !Array.isArray(value.frames) ||
    !value.frames.every(isTimelineFrame) ||
    !isStrictlyOrdered(value.frames.map((frame) => frame.time)) ||
    !Array.isArray(value.gaps) ||
    !value.gaps.every(isTimelineGap) ||
    !isRecord(statistics) ||
    !isNonNegativeNumber(statistics.archivedFrames) ||
    statistics.publishedFrames !== value.frames.length ||
    !isNonNegativeNumber(statistics.discardedDuplicates) ||
    !isNonNegativeNumber(statistics.invalidReports)
  ) {
    return false;
  }

  if (value.frames.length === 0) {
    return (
      window.start === null &&
      window.end === null &&
      value.latestFrameTime === null &&
      value.latestProductTime === null &&
      value.timeBasis === null &&
      value.gaps.length === 0
    );
  }

  return (
    isDateTime(window.start) &&
    isDateTime(window.end) &&
    isDateTime(value.latestFrameTime) &&
    (value.latestProductTime === null || isDateTime(value.latestProductTime)) &&
    isTimeBasis(value.timeBasis) &&
    value.latestFrameTime === value.frames.at(-1)?.time
  );
}

export function buildTimelineSlots(manifest: RadarManifest): TimelineSlot[] {
  const frameTimes = new Set(manifest.frames.map((frame) => frame.time));
  const slots: TimelineSlot[] = manifest.frames.map((frame) => ({
    kind: 'frame',
    id: frame.id,
    time: frame.time,
    frame,
  }));
  for (const gap of manifest.gaps) {
    for (const time of gap.expectedTimes) {
      if (!frameTimes.has(time)) {
        slots.push({
          kind: 'gap',
          id: `gap-${time}`,
          time,
          gap,
        });
      }
    }
  }
  return slots.sort(
    (left, right) => Date.parse(left.time) - Date.parse(right.time),
  );
}

export function formatMadridTime(value: string): string {
  return new Intl.DateTimeFormat('es-ES', {
    timeZone: MADRID_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

export function formatMadridDate(value: string): string {
  return new Intl.DateTimeFormat('es-ES', {
    timeZone: MADRID_TIME_ZONE,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(new Date(value));
}

export function formatMadridTimeZoneName(value: string): string {
  return (
    new Intl.DateTimeFormat('es-ES', {
      timeZone: MADRID_TIME_ZONE,
      timeZoneName: 'short',
    })
      .formatToParts(new Date(value))
      .find((part) => part.type === 'timeZoneName')?.value ?? MADRID_TIME_ZONE
  );
}

function isTimelineFrame(value: unknown): value is RadarTimelineFrame {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    isDateTime(value.time) &&
    (value.timeSource === 'productTime' ||
      value.timeSource === 'retrievedAt') &&
    (value.productTime === null || isDateTime(value.productTime)) &&
    isDateTime(value.retrievedAt) &&
    isDateTime(value.lastRetrievedAt) &&
    /^sha256:[0-9a-f]{64}$/.test(String(value.sourceHash)) &&
    typeof value.rawUrl === 'string' &&
    value.rawUrl.startsWith('/') &&
    typeof value.imageUrl === 'string' &&
    value.imageUrl.startsWith('/') &&
    isMapCoordinates(value.imageCoordinates) &&
    value.status === 'available'
  );
}

function isMapCoordinates(value: unknown): value is MapCoordinates {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every(
      (coordinate) =>
        Array.isArray(coordinate) &&
        coordinate.length === 2 &&
        coordinate.every(
          (component) =>
            typeof component === 'number' && Number.isFinite(component),
        ),
    )
  );
}

function isTimelineGap(value: unknown): value is RadarTimelineGap {
  return (
    isRecord(value) &&
    (value.after === null || isDateTime(value.after)) &&
    isDateTime(value.before) &&
    isPositiveNumber(value.expectedCadenceMinutes) &&
    typeof value.missingCount === 'number' &&
    Number.isInteger(value.missingCount) &&
    value.missingCount > 0 &&
    Array.isArray(value.expectedTimes) &&
    value.expectedTimes.length === value.missingCount &&
    value.expectedTimes.every(isDateTime) &&
    isTimeBasis(value.timeBasis)
  );
}

function isTimeBasis(
  value: unknown,
): value is 'productTime' | 'retrievedAt' | 'mixed' {
  return (
    value === 'productTime' || value === 'retrievedAt' || value === 'mixed'
  );
}

function isStrictlyOrdered(values: string[]): boolean {
  return values.every(
    (value, index) =>
      index === 0 || Date.parse(values[index - 1]!) < Date.parse(value),
  );
}

function isDateTime(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
