export function formatDataAge(value: string, now = Date.now()): string {
  const elapsedMinutes = Math.max(
    0,
    Math.floor((now - Date.parse(value)) / 60_000),
  );
  if (elapsedMinutes < 1) {
    return 'hace menos de 1 min';
  }
  if (elapsedMinutes < 60) {
    return `hace ${elapsedMinutes} min`;
  }
  const hours = Math.floor(elapsedMinutes / 60);
  const minutes = elapsedMinutes % 60;
  if (hours < 24) {
    return `hace ${hours} h${minutes ? ` ${minutes} min` : ''}`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return `hace ${days} ${days === 1 ? 'día' : 'días'}${
    remainingHours ? ` ${remainingHours} h` : ''
  }`;
}
