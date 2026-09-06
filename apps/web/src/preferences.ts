export function readStoredString(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function readStoredNumber(
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

export function writeStoredValue(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Las preferencias son opcionales en contextos con almacenamiento bloqueado.
  }
}
