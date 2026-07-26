export type Coordinate = [number, number];

export type MapImageCoordinates = [
  Coordinate,
  Coordinate,
  Coordinate,
  Coordinate,
];

export interface CalibrationControlPoint {
  id: string;
  label: string;
  coordinates: Coordinate;
  errorKilometres: number;
}

export interface RadarFrameReport {
  attribution: string;
  radar: {
    aemetCode: string;
    name: string;
    coordinates: Coordinate;
    rangeKilometres: number;
  };
  output: {
    file: string;
    width: number;
    height: number;
    crs: string;
    pixelSizeMetres: number;
    maplibreCoordinates: MapImageCoordinates;
  };
  calibration: {
    status: 'pass';
    controlPointCount: number;
    meanErrorKilometres: number;
    maximumErrorKilometres: number;
    acceptedMaximumErrorPixels: number;
    controlPoints: CalibrationControlPoint[];
  };
  debug: {
    coverageRing: Coordinate[];
  };
}

export const FRAME_REPORT_URL = '/radar/regional-mu/georeferencing.json';

export function isRadarFrameReport(value: unknown): value is RadarFrameReport {
  if (!isRecord(value)) {
    return false;
  }
  const radar = value.radar;
  const output = value.output;
  const calibration = value.calibration;
  const debug = value.debug;
  return (
    typeof value.attribution === 'string' &&
    isRecord(radar) &&
    radar.aemetCode === 'FTN' &&
    typeof radar.name === 'string' &&
    isCoordinate(radar.coordinates) &&
    typeof radar.rangeKilometres === 'number' &&
    isRecord(output) &&
    typeof output.file === 'string' &&
    typeof output.width === 'number' &&
    typeof output.height === 'number' &&
    output.crs === 'EPSG:3857' &&
    typeof output.pixelSizeMetres === 'number' &&
    isMapCoordinates(output.maplibreCoordinates) &&
    isRecord(calibration) &&
    calibration.status === 'pass' &&
    typeof calibration.controlPointCount === 'number' &&
    typeof calibration.meanErrorKilometres === 'number' &&
    typeof calibration.maximumErrorKilometres === 'number' &&
    typeof calibration.acceptedMaximumErrorPixels === 'number' &&
    Array.isArray(calibration.controlPoints) &&
    calibration.controlPoints.every(isControlPoint) &&
    isRecord(debug) &&
    Array.isArray(debug.coverageRing) &&
    debug.coverageRing.every(isCoordinate)
  );
}

function isControlPoint(value: unknown): value is CalibrationControlPoint {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.label === 'string' &&
    isCoordinate(value.coordinates) &&
    typeof value.errorKilometres === 'number'
  );
}

function isMapCoordinates(value: unknown): value is MapImageCoordinates {
  return (
    Array.isArray(value) && value.length === 4 && value.every(isCoordinate)
  );
}

function isCoordinate(value: unknown): value is Coordinate {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number'
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
