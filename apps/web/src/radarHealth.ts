export const RADAR_HEALTH_URL = '/status/health.json';

export type RadarHealthStatus = 'current' | 'delayed' | 'no-data' | 'error';

export interface RadarHealthProduct {
  id: string;
  label: string;
  status: RadarHealthStatus;
  lastFrameTime: string | null;
  lastPollAt: string | null;
  lastError: unknown;
}

export interface RadarHealth {
  schemaVersion: 1;
  generatedAt: string;
  status: 'ok' | 'degraded' | 'no-data';
  products: RadarHealthProduct[];
}

export function isRadarHealth(value: unknown): value is RadarHealth {
  return (
    isRecord(value) &&
    value.schemaVersion === 1 &&
    isDateTime(value.generatedAt) &&
    (value.status === 'ok' ||
      value.status === 'degraded' ||
      value.status === 'no-data') &&
    Array.isArray(value.products) &&
    value.products.every(isRadarHealthProduct)
  );
}

function isRadarHealthProduct(value: unknown): value is RadarHealthProduct {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.label === 'string' &&
    (value.status === 'current' ||
      value.status === 'delayed' ||
      value.status === 'no-data' ||
      value.status === 'error') &&
    (value.lastFrameTime === null || isDateTime(value.lastFrameTime)) &&
    (value.lastPollAt === null || isDateTime(value.lastPollAt))
  );
}

function isDateTime(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
