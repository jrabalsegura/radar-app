export interface RadarPerformanceMetrics {
  appReadyMilliseconds?: number;
  cumulativeLayoutShift?: number;
  firstContentfulPaintMilliseconds?: number;
  interactionToNextPaintMilliseconds?: number;
  largestContentfulPaintMilliseconds?: number;
}

declare global {
  interface Window {
    __RADAR_PERFORMANCE__?: RadarPerformanceMetrics;
  }
}

const APP_START_MARK = 'radar-app-start';
const APP_READY_MARK = 'radar-app-ready';
let appReadyRecorded = false;

export function startPerformanceMetrics(): void {
  window.__RADAR_PERFORMANCE__ = {};
  performance.mark(APP_START_MARK);

  const firstContentfulPaint = performance
    .getEntriesByName('first-contentful-paint')
    .at(0);
  if (firstContentfulPaint) {
    metrics().firstContentfulPaintMilliseconds = firstContentfulPaint.startTime;
  }

  observe('paint', (entries) => {
    const entry = entries.find(
      (candidate) => candidate.name === 'first-contentful-paint',
    );
    if (entry) {
      metrics().firstContentfulPaintMilliseconds = entry.startTime;
    }
  });
  observe('largest-contentful-paint', (entries) => {
    const entry = entries.at(-1);
    if (entry) {
      metrics().largestContentfulPaintMilliseconds = entry.startTime;
    }
  });
  observe('layout-shift', (entries) => {
    for (const entry of entries) {
      const shift = entry as PerformanceEntry & {
        hadRecentInput?: boolean;
        value?: number;
      };
      if (!shift.hadRecentInput) {
        metrics().cumulativeLayoutShift =
          (metrics().cumulativeLayoutShift ?? 0) + (shift.value ?? 0);
      }
    }
  });
  observe('event', (entries) => {
    const longestInteraction = Math.max(
      metrics().interactionToNextPaintMilliseconds ?? 0,
      ...entries.map((entry) => entry.duration),
    );
    metrics().interactionToNextPaintMilliseconds = longestInteraction;
  });
}

export function recordAppReady(): void {
  if (appReadyRecorded) {
    return;
  }
  appReadyRecorded = true;
  if (performance.getEntriesByName(APP_START_MARK).length === 0) {
    performance.mark(APP_START_MARK);
  }
  performance.mark(APP_READY_MARK);
  performance.measure('radar-app-interactive', APP_START_MARK, APP_READY_MARK);
  const measure = performance.getEntriesByName('radar-app-interactive').at(-1);
  if (measure) {
    metrics().appReadyMilliseconds = measure.duration;
  }
}

function metrics(): RadarPerformanceMetrics {
  window.__RADAR_PERFORMANCE__ ??= {};
  return window.__RADAR_PERFORMANCE__;
}

function observe(
  type: string,
  onEntries: (entries: PerformanceEntry[]) => void,
): void {
  if (typeof PerformanceObserver === 'undefined') {
    return;
  }
  try {
    const observer = new PerformanceObserver((list) =>
      onEntries(list.getEntries()),
    );
    observer.observe({ type, buffered: true });
  } catch {
    // Algunos navegadores todavía no implementan todos los tipos de entrada.
  }
}
