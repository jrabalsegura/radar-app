export type DataSource = 'network' | 'cache';

export interface ResilientData<T> {
  data: T;
  source: DataSource;
  savedAt: string;
}

interface CacheEnvelope {
  schemaVersion: 1;
  savedAt: string;
  value: unknown;
}

const CACHE_PREFIX = 'aemet-radar:v1:';

export async function loadResilientJson<T>(
  url: string,
  cacheId: string,
  isValid: (value: unknown) => value is T,
  signal?: AbortSignal,
): Promise<ResilientData<T>> {
  try {
    const response = await fetch(url, {
      ...(signal ? { signal } : {}),
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`La petición a ${url} respondió ${response.status}.`);
    }
    const value: unknown = await response.json();
    if (!isValid(value)) {
      throw new Error(`La respuesta de ${url} no cumple el contrato.`);
    }
    const serviceWorkerCache =
      response.headers?.get?.('X-Radar-Cache') === 'hit';
    if (serviceWorkerCache) {
      const localCopy = readCache(cacheId, isValid);
      return {
        data: value,
        source: 'cache',
        savedAt: localCopy?.savedAt ?? new Date().toISOString(),
      };
    }
    const savedAt = new Date().toISOString();
    writeCache(cacheId, { schemaVersion: 1, savedAt, value });
    return { data: value, source: 'network', savedAt };
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    const cached = readCache(cacheId, isValid);
    if (cached) {
      return cached;
    }
    throw error;
  }
}

export function cacheKey(cacheId: string): string {
  return `${CACHE_PREFIX}${cacheId}`;
}

function readCache<T>(
  cacheId: string,
  isValid: (value: unknown) => value is T,
): ResilientData<T> | null {
  try {
    const serialized = window.localStorage.getItem(cacheKey(cacheId));
    if (!serialized) {
      return null;
    }
    const envelope: unknown = JSON.parse(serialized);
    if (
      !isRecord(envelope) ||
      envelope.schemaVersion !== 1 ||
      !isDateTime(envelope.savedAt) ||
      !isValid(envelope.value)
    ) {
      window.localStorage.removeItem(cacheKey(cacheId));
      return null;
    }
    return {
      data: envelope.value,
      source: 'cache',
      savedAt: envelope.savedAt,
    };
  } catch {
    return null;
  }
}

function writeCache(cacheId: string, envelope: CacheEnvelope): void {
  try {
    window.localStorage.setItem(cacheKey(cacheId), JSON.stringify(envelope));
  } catch {
    // El modo privado o una cuota agotada no deben impedir usar los datos de red.
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function isDateTime(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
