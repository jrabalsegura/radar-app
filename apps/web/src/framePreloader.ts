import type { RadarTimelineFrame, TimelineSlot } from './radarManifest';

const frameLoads = new Map<string, Promise<void>>();
export const MAX_PRELOADED_FRAMES = 8;
const MAX_TRACKED_LOADS = 12;

export function preloadFrame(url: string): Promise<void> {
  const existing = frameLoads.get(url);
  if (existing) {
    return existing;
  }
  const pending = new Promise<void>((resolve, reject) => {
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => resolve();
    image.onerror = () => reject(new Error(`No se pudo precargar ${url}`));
    image.src = url;
  }).catch((error: unknown) => {
    frameLoads.delete(url);
    throw error;
  });
  frameLoads.set(url, pending);
  pruneTrackedLoads(url);
  return pending;
}

export function prioritizedFrameUrls(
  slots: TimelineSlot[],
  selectedIndex: number,
): string[] {
  const frames = slots
    .map((slot, index) =>
      slot.kind === 'frame' ? { frame: slot.frame, index } : null,
    )
    .filter(
      (item): item is { frame: RadarTimelineFrame; index: number } =>
        item !== null,
    );
  const latest = frames.at(-1);
  return frames
    .sort((left, right) => {
      const leftLatest = left === latest ? 0 : 1;
      const rightLatest = right === latest ? 0 : 1;
      return (
        leftLatest - rightLatest ||
        Math.abs(left.index - selectedIndex) -
          Math.abs(right.index - selectedIndex) ||
        right.index - left.index
      );
    })
    .map(({ frame }) => frame.imageUrl)
    .slice(0, MAX_PRELOADED_FRAMES);
}

export function preloadInPriorityOrder(
  slots: TimelineSlot[],
  selectedIndex: number,
): () => void {
  let cancelled = false;
  const urls = prioritizedFrameUrls(slots, selectedIndex);
  void (async () => {
    for (const url of urls) {
      if (cancelled) {
        return;
      }
      try {
        await preloadFrame(url);
      } catch {
        // El mapa mantiene el último fotograma válido y mostrará el error de carga.
      }
    }
  })();
  return () => {
    cancelled = true;
  };
}

export function resetFramePreloaderForTests(): void {
  frameLoads.clear();
}

function pruneTrackedLoads(preservedUrl: string): void {
  while (frameLoads.size > MAX_TRACKED_LOADS) {
    const oldestUrl = frameLoads.keys().next().value as string | undefined;
    if (!oldestUrl) {
      return;
    }
    if (oldestUrl === preservedUrl && frameLoads.size === 1) {
      return;
    }
    frameLoads.delete(oldestUrl);
  }
}
