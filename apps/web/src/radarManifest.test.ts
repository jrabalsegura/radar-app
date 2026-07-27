import { describe, expect, it } from 'vitest';

import { formatMadridTime, formatMadridTimeZoneName } from './radarManifest';

describe('formato horario de Madrid', () => {
  it('aplica CET en invierno', () => {
    const winterUtc = '2026-01-15T12:00:00Z';

    expect(formatMadridTime(winterUtc)).toBe('13:00');
    expect(formatMadridTimeZoneName(winterUtc)).toBe('CET');
  });

  it('aplica CEST en verano', () => {
    const summerUtc = '2026-07-15T12:00:00Z';

    expect(formatMadridTime(summerUtc)).toBe('14:00');
    expect(formatMadridTimeZoneName(summerUtc)).toBe('CEST');
  });
});
