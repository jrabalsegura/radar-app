import type { RadarIndexEntry, RegionalRadarIndexEntry } from './radarIndex';

export type LongitudeLatitude = [longitude: number, latitude: number];

export function closestRegionalRadar(
  radars: RadarIndexEntry[],
  location: LongitudeLatitude,
): RegionalRadarIndexEntry | null {
  const regional = radars.filter(
    (radar): radar is RegionalRadarIndexEntry => radar.kind === 'regional',
  );
  return (
    regional.reduce<RegionalRadarIndexEntry | null>((closest, candidate) => {
      if (!closest) {
        return candidate;
      }
      return haversineKilometres(location, candidate.coordinates) <
        haversineKilometres(location, closest.coordinates)
        ? candidate
        : closest;
    }, null) ?? null
  );
}

export function haversineKilometres(
  first: LongitudeLatitude,
  second: LongitudeLatitude,
): number {
  const earthRadiusKilometres = 6371;
  const latitudeDelta = toRadians(second[1] - first[1]);
  const longitudeDelta = toRadians(second[0] - first[0]);
  const firstLatitude = toRadians(first[1]);
  const secondLatitude = toRadians(second[1]);
  const halfChord =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(firstLatitude) *
      Math.cos(secondLatitude) *
      Math.sin(longitudeDelta / 2) ** 2;
  return (
    2 *
    earthRadiusKilometres *
    Math.atan2(Math.sqrt(halfChord), Math.sqrt(1 - halfChord))
  );
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}
