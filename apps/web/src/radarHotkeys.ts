export const RADAR_HOTKEYS: Readonly<Record<string, string>> = {
  national: 'e',
  'regional-am': 'a',
  'regional-sa': 't',
  'regional-pm': 'i',
  'regional-ba': 'b',
  'regional-cc': 'c',
  'regional-co': 'o',
  'regional-ma': 'm',
  'regional-ml': 'g',
  'regional-mu': 'n',
  'regional-vd': 'p',
  'regional-ca': 'l',
  'regional-se': 's',
  'regional-va': 'v',
  'regional-ss': 'y',
  'regional-za': 'z',
};

const RADAR_IDS_BY_HOTKEY = new Map(
  Object.entries(RADAR_HOTKEYS).map(([radarId, hotkey]) => [hotkey, radarId]),
);

export function radarHotkey(radarId: string): string | null {
  return RADAR_HOTKEYS[radarId] ?? null;
}

export function radarIdForHotkey(key: string): string | null {
  if (key.length !== 1) {
    return null;
  }
  return RADAR_IDS_BY_HOTKEY.get(key.toLowerCase()) ?? null;
}

export function radarLabelWithHotkey(radarId: string, label: string): string {
  const hotkey = radarHotkey(radarId);
  return hotkey ? `${label} (${hotkey.toUpperCase()})` : label;
}
