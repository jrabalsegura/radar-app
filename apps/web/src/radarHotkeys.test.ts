import { describe, expect, it } from 'vitest';

import {
  radarHotkey,
  radarIdForHotkey,
  radarLabelWithHotkey,
  RADAR_HOTKEYS,
} from './radarHotkeys';

describe('atajos de radar', () => {
  it('asigna una tecla distinta a cada producto del catálogo', () => {
    const hotkeys = Object.values(RADAR_HOTKEYS);

    expect(Object.keys(RADAR_HOTKEYS)).toHaveLength(16);
    expect(new Set(hotkeys).size).toBe(16);
  });

  it('mantiene los atajos acordados y acepta mayúsculas', () => {
    expect(radarHotkey('regional-am')).toBe('a');
    expect(radarHotkey('regional-ma')).toBe('m');
    expect(radarHotkey('regional-ml')).toBe('g');
    expect(radarHotkey('regional-mu')).toBe('n');
    expect(radarHotkey('regional-ss')).toBe('y');
    expect(radarHotkey('regional-za')).toBe('z');
    expect(radarIdForHotkey('A')).toBe('regional-am');
    expect(radarIdForHotkey('ArrowLeft')).toBeNull();
  });

  it('muestra la tecla en mayúscula junto al nombre', () => {
    expect(radarLabelWithHotkey('regional-ml', 'Málaga')).toBe('Málaga (G)');
    expect(radarLabelWithHotkey('desconocido', 'Otro')).toBe('Otro');
  });
});
