"""Georreferenciación reproducible de radares regionales."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image, UnidentifiedImageError
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import CRSError, ProjError

from aemet_radar.errors import GeoreferencingError
from aemet_radar.storage import atomic_write_bytes, atomic_write_json

PROCESSOR_ID = "regional-georeference-v1"
TARGET_CRS = "EPSG:3857"


@dataclass(frozen=True, slots=True)
class Pixel:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Radar:
    code: str
    name: str
    longitude: float
    latitude: float
    range_kilometres: float


@dataclass(frozen=True, slots=True)
class SourceRaster:
    width: int
    height: int
    center: Pixel
    metres_per_pixel: float
    projection: str


@dataclass(frozen=True, slots=True)
class OutputRaster:
    crs: str
    pixel_size_metres: float
    resampling: str


@dataclass(frozen=True, slots=True)
class ControlPoint:
    id: str
    label: str
    longitude: float
    latitude: float
    observed: Pixel


@dataclass(frozen=True, slots=True)
class GeoreferencingConfig:
    schema_version: int
    product_id: str
    processor: str
    radar: Radar
    source: SourceRaster
    output: OutputRaster
    control_points: tuple[ControlPoint, ...]
    maximum_error_pixels: float
    validation_mode: str
    validation_method: str
    validation_reference: str

    @property
    def source_crs(self) -> CRS:
        try:
            return CRS.from_user_input(self.source.projection)
        except CRSError as exc:
            raise GeoreferencingError("La proyección de origen no es válida.") from exc


@dataclass(frozen=True, slots=True)
class GeoreferencingResult:
    image_path: Path
    report_path: Path
    report: dict[str, object]


def load_georeferencing_config(path: Path) -> GeoreferencingConfig:
    """Carga y valida una calibración regional versionada."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GeoreferencingError(
            "No se pudo leer la configuración de georreferenciación."
        ) from exc
    except json.JSONDecodeError as exc:
        raise GeoreferencingError(
            "La configuración de georreferenciación no contiene JSON válido."
        ) from exc
    if not isinstance(payload, dict):
        raise GeoreferencingError("La configuración de georreferenciación debe ser un objeto JSON.")

    radar_payload = _required_mapping(payload, "radar")
    source_payload = _required_mapping(payload, "sourceRaster")
    center_payload = _required_mapping(source_payload, "centerPixel")
    source_crs_payload = _required_mapping(source_payload, "crs")
    output_payload = _required_mapping(payload, "output")
    calibration_payload = _required_mapping(payload, "calibration")
    controls_payload = _required_list(calibration_payload, "controlPoints")

    config = GeoreferencingConfig(
        schema_version=_required_int(payload, "schemaVersion"),
        product_id=_required_string(payload, "productId"),
        processor=_required_string(payload, "processor"),
        radar=Radar(
            code=_required_string(radar_payload, "aemetCode"),
            name=_required_string(radar_payload, "name"),
            longitude=_required_float(radar_payload, "longitude"),
            latitude=_required_float(radar_payload, "latitude"),
            range_kilometres=_required_float(radar_payload, "rangeKilometres"),
        ),
        source=SourceRaster(
            width=_required_int(source_payload, "width"),
            height=_required_int(source_payload, "height"),
            center=Pixel(
                x=_required_float(center_payload, "x"),
                y=_required_float(center_payload, "y"),
            ),
            metres_per_pixel=_required_float(source_payload, "metresPerPixel"),
            projection=_required_string(source_crs_payload, "proj"),
        ),
        output=OutputRaster(
            crs=_required_string(output_payload, "crs"),
            pixel_size_metres=_required_float(output_payload, "pixelSizeMetres"),
            resampling=_required_string(output_payload, "resampling"),
        ),
        control_points=tuple(_parse_control_point(item) for item in controls_payload),
        maximum_error_pixels=_required_float(calibration_payload, "maximumAcceptedErrorPixels"),
        validation_mode=_optional_string(
            calibration_payload,
            "validationMode",
            "control-points",
        ),
        validation_method=_optional_string(
            calibration_payload,
            "method",
            "Puntos de control geográficos versionados.",
        ),
        validation_reference=_optional_string(
            calibration_payload,
            "reference",
            "configuración versionada",
        ),
    )
    _validate_config(config, source_payload)
    _calibration_report(config)
    return config


def georeference_overlay(
    source_path: Path,
    *,
    config_path: Path | None = None,
    configuration: GeoreferencingConfig | None = None,
    configuration_sha256: str | None = None,
    output_dir: Path,
) -> GeoreferencingResult:
    """Reproyecta una capa RGBA regional a una imagen Web Mercator."""

    if (config_path is None) == (configuration is None):
        raise GeoreferencingError("Debe indicarse exactamente una configuración regional.")
    config = (
        load_georeferencing_config(config_path)
        if config_path is not None
        else cast(GeoreferencingConfig, configuration)
    )
    resolved_configuration_sha256 = (
        f"sha256:{hashlib.sha256(config_path.read_bytes()).hexdigest()}"
        if config_path is not None
        else configuration_sha256
    )
    if resolved_configuration_sha256 is None:
        raise GeoreferencingError("La configuración en memoria requiere un hash verificable.")
    source_bytes = _read_source(source_path)
    try:
        with Image.open(BytesIO(source_bytes)) as opened:
            opened.load()
            source_format = opened.format
            source_mode = opened.mode
            source_size = opened.size
            source = opened.copy()
    except (OSError, UnidentifiedImageError) as exc:
        raise GeoreferencingError("La capa de origen no es una imagen válida.") from exc

    expected_size = (config.source.width, config.source.height)
    if source_format != "PNG" or source_mode != "RGBA" or source_size != expected_size:
        raise GeoreferencingError(
            "La capa no coincide con el PNG RGBA configurado para regional-v1.",
            details={
                "expectedFormat": "PNG",
                "actualFormat": source_format,
                "expectedMode": "RGBA",
                "actualMode": source_mode,
                "expectedSize": list(expected_size),
                "actualSize": list(source_size),
            },
        )

    bounds = _target_bounds(config)
    projected = _warp_nearest(source, config, bounds)
    image_bytes = _png_bytes(projected)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / "overlay-3857.png"
    report_path = output_dir / "georeferencing.json"
    atomic_write_bytes(image_path, image_bytes)

    coordinates = _maplibre_coordinates(bounds)
    calibration = _calibration_report(config)
    report: dict[str, object] = {
        "schemaVersion": 1,
        "productId": config.product_id,
        "processor": config.processor,
        "radar": {
            "aemetCode": config.radar.code,
            "name": config.radar.name,
            "coordinates": [
                config.radar.longitude,
                config.radar.latitude,
            ],
            "rangeKilometres": config.radar.range_kilometres,
        },
        "source": {
            "sha256": f"sha256:{hashlib.sha256(source_bytes).hexdigest()}",
            "width": config.source.width,
            "height": config.source.height,
            "crs": config.source.projection,
            "metresPerPixel": config.source.metres_per_pixel,
            "orientation": "north-up",
        },
        "output": {
            "file": image_path.name,
            "sha256": f"sha256:{hashlib.sha256(image_bytes).hexdigest()}",
            "width": projected.width,
            "height": projected.height,
            "crs": config.output.crs,
            "pixelSizeMetres": config.output.pixel_size_metres,
            "resampling": config.output.resampling,
            "webMercatorBoundsMetres": {
                "west": _rounded(bounds[0], 3),
                "south": _rounded(bounds[1], 3),
                "east": _rounded(bounds[2], 3),
                "north": _rounded(bounds[3], 3),
            },
            "maplibreCoordinates": coordinates,
        },
        "calibration": calibration,
        "debug": {
            "coverageRing": coverage_ring(config.radar),
        },
        "configuration": {"sha256": resolved_configuration_sha256},
        "attribution": "Datos radar © AEMET",
    }
    atomic_write_json(report_path, report)
    return GeoreferencingResult(
        image_path=image_path,
        report_path=report_path,
        report=report,
    )


def _validate_config(
    config: GeoreferencingConfig,
    source_payload: dict[str, object],
) -> None:
    if config.schema_version != 1:
        raise GeoreferencingError("Solo se admite schemaVersion 1.")
    if not config.product_id.startswith("regional-") or config.processor != PROCESSOR_ID:
        raise GeoreferencingError("La configuración no corresponde al procesador regional.")
    if config.source.width <= 0 or config.source.height <= 0:
        raise GeoreferencingError("Las dimensiones de origen deben ser positivas.")
    if config.source.metres_per_pixel <= 0 or config.output.pixel_size_metres <= 0:
        raise GeoreferencingError("Las resoluciones deben ser positivas.")
    if not (0 <= config.source.center.x < config.source.width):
        raise GeoreferencingError("El centro X queda fuera del raster.")
    if not (0 <= config.source.center.y < config.source.height):
        raise GeoreferencingError("El centro Y queda fuera del raster.")
    if _required_string(source_payload, "orientation") != "north-up":
        raise GeoreferencingError("La orientación de regional-georeference-v1 es norte arriba.")
    if config.output.crs != TARGET_CRS or config.output.resampling != "nearest":
        raise GeoreferencingError(
            "regional-georeference-v1 requiere EPSG:3857 y vecino más próximo."
        )
    if config.radar.range_kilometres <= 0:
        raise GeoreferencingError("El alcance del radar debe ser positivo.")
    if config.validation_mode not in {"control-points", "official-geometry"}:
        raise GeoreferencingError("El modo de validación regional no está soportado.")
    if config.validation_mode == "control-points" and len(config.control_points) < 3:
        raise GeoreferencingError("La calibración requiere al menos tres puntos de control.")
    if config.validation_mode == "official-geometry" and config.control_points:
        raise GeoreferencingError(
            "official-geometry no debe declarar puntos de control implícitos."
        )
    if config.maximum_error_pixels <= 0:
        raise GeoreferencingError("El umbral de error debe ser positivo.")

    try:
        centre_to_source = Transformer.from_crs("EPSG:4326", config.source_crs, always_xy=True)
        centre_x, centre_y = centre_to_source.transform(
            config.radar.longitude, config.radar.latitude
        )
    except ProjError as exc:
        raise GeoreferencingError("No se pudo construir la transformación de origen.") from exc
    if math.hypot(centre_x, centre_y) > 0.001:
        raise GeoreferencingError("La proyección no está centrada en el radar configurado.")


def _calibration_report(config: GeoreferencingConfig) -> dict[str, object]:
    if config.validation_mode == "official-geometry":
        return {
            "validationMode": config.validation_mode,
            "method": config.validation_method,
            "reference": config.validation_reference,
            "controlPointCount": 0,
            "meanErrorPixels": None,
            "meanErrorKilometres": None,
            "maximumErrorPixels": None,
            "maximumErrorKilometres": None,
            "rmsErrorPixels": None,
            "acceptedMaximumErrorPixels": config.maximum_error_pixels,
            "status": "pass",
            "controlPoints": [],
        }
    try:
        transformer = Transformer.from_crs("EPSG:4326", config.source_crs, always_xy=True)
        rows: list[dict[str, object]] = []
        errors: list[float] = []
        for point in config.control_points:
            projected_x, projected_y = transformer.transform(point.longitude, point.latitude)
            expected = Pixel(
                x=config.source.center.x + projected_x / config.source.metres_per_pixel,
                y=config.source.center.y - projected_y / config.source.metres_per_pixel,
            )
            error_pixels = math.hypot(
                expected.x - point.observed.x,
                expected.y - point.observed.y,
            )
            errors.append(error_pixels)
            rows.append(
                {
                    "id": point.id,
                    "label": point.label,
                    "coordinates": [point.longitude, point.latitude],
                    "observedPixel": {
                        "x": point.observed.x,
                        "y": point.observed.y,
                    },
                    "expectedPixel": {
                        "x": _rounded(expected.x, 6),
                        "y": _rounded(expected.y, 6),
                    },
                    "errorPixels": _rounded(error_pixels, 6),
                    "errorKilometres": _rounded(
                        error_pixels * config.source.metres_per_pixel / 1000,
                        6,
                    ),
                }
            )
    except ProjError as exc:
        raise GeoreferencingError("No se pudieron calcular los puntos de control.") from exc

    mean_error = sum(errors) / len(errors)
    maximum_error = max(errors)
    rms_error = math.sqrt(sum(value * value for value in errors) / len(errors))
    if maximum_error > config.maximum_error_pixels:
        raise GeoreferencingError(
            "La calibración supera el error máximo permitido.",
            details={
                "maximumErrorPixels": _rounded(maximum_error, 6),
                "acceptedErrorPixels": config.maximum_error_pixels,
            },
        )
    return {
        "validationMode": config.validation_mode,
        "method": config.validation_method,
        "reference": config.validation_reference,
        "controlPointCount": len(rows),
        "meanErrorPixels": _rounded(mean_error, 6),
        "meanErrorKilometres": _rounded(mean_error * config.source.metres_per_pixel / 1000, 6),
        "maximumErrorPixels": _rounded(maximum_error, 6),
        "maximumErrorKilometres": _rounded(
            maximum_error * config.source.metres_per_pixel / 1000, 6
        ),
        "rmsErrorPixels": _rounded(rms_error, 6),
        "acceptedMaximumErrorPixels": config.maximum_error_pixels,
        "status": "pass",
        "controlPoints": rows,
    }


def _target_bounds(config: GeoreferencingConfig) -> tuple[float, float, float, float]:
    try:
        transformer = Transformer.from_crs(config.source_crs, config.output.crs, always_xy=True)
        samples: list[tuple[float, float]] = []
        last_x = config.source.width - 0.5
        last_y = config.source.height - 0.5
        for index in range(config.source.width + 1):
            x = index - 0.5
            samples.extend(
                (
                    _source_pixel_to_metres(config, x, -0.5),
                    _source_pixel_to_metres(config, x, last_y),
                )
            )
        for index in range(config.source.height + 1):
            y = index - 0.5
            samples.extend(
                (
                    _source_pixel_to_metres(config, -0.5, y),
                    _source_pixel_to_metres(config, last_x, y),
                )
            )
        eastings, northings = transformer.transform(
            [item[0] for item in samples],
            [item[1] for item in samples],
        )
    except ProjError as exc:
        raise GeoreferencingError("No se pudo calcular la extensión Web Mercator.") from exc

    resolution = config.output.pixel_size_metres
    west = math.floor(min(eastings) / resolution) * resolution
    south = math.floor(min(northings) / resolution) * resolution
    east = math.ceil(max(eastings) / resolution) * resolution
    north = math.ceil(max(northings) / resolution) * resolution
    return west, south, east, north


def _warp_nearest(
    source: Image.Image,
    config: GeoreferencingConfig,
    bounds: tuple[float, float, float, float],
) -> Image.Image:
    west, south, east, north = bounds
    resolution = config.output.pixel_size_metres
    width = round((east - west) / resolution)
    height = round((north - south) / resolution)
    if width <= 0 or height <= 0:
        raise GeoreferencingError("La extensión de salida no produce un raster válido.")

    try:
        inverse = Transformer.from_crs(config.output.crs, config.source_crs, always_xy=True)
        target_x = [west + (column + 0.5) * resolution for column in range(width)]
        source_bytes = source.tobytes()
        target_bytes = bytearray(width * height * 4)
        for row in range(height):
            target_y = north - (row + 0.5) * resolution
            projected_x, projected_y = inverse.transform(target_x, [target_y] * width)
            row_offset = row * width * 4
            for column, (metres_x, metres_y) in enumerate(
                zip(projected_x, projected_y, strict=True)
            ):
                if math.hypot(metres_x, metres_y) > config.radar.range_kilometres * 1000:
                    continue
                source_x = math.floor(
                    config.source.center.x + metres_x / config.source.metres_per_pixel + 0.5
                )
                source_y = math.floor(
                    config.source.center.y - metres_y / config.source.metres_per_pixel + 0.5
                )
                if 0 <= source_x < source.width and 0 <= source_y < source.height:
                    source_offset = (source_y * source.width + source_x) * 4
                    target_offset = row_offset + column * 4
                    target_bytes[target_offset : target_offset + 4] = source_bytes[
                        source_offset : source_offset + 4
                    ]
    except ProjError as exc:
        raise GeoreferencingError("No se pudo reproyectar la capa.") from exc
    return Image.frombytes("RGBA", (width, height), bytes(target_bytes))


def _source_pixel_to_metres(
    config: GeoreferencingConfig,
    x: float,
    y: float,
) -> tuple[float, float]:
    return (
        (x - config.source.center.x) * config.source.metres_per_pixel,
        (config.source.center.y - y) * config.source.metres_per_pixel,
    )


def _maplibre_coordinates(
    bounds: tuple[float, float, float, float],
) -> list[list[float]]:
    west, south, east, north = bounds
    try:
        transformer = Transformer.from_crs(TARGET_CRS, "EPSG:4326", always_xy=True)
        corners = (
            transformer.transform(west, north),
            transformer.transform(east, north),
            transformer.transform(east, south),
            transformer.transform(west, south),
        )
    except ProjError as exc:
        raise GeoreferencingError("No se pudieron calcular las esquinas para MapLibre.") from exc
    return [[_rounded(lon, 8), _rounded(lat, 8)] for lon, lat in corners]


def coverage_ring(radar: Radar) -> list[list[float]]:
    """Devuelve el perímetro geodésico utilizado por el mapa de depuración."""

    geod = Geod(ellps="WGS84")
    result: list[list[float]] = []
    for bearing in range(0, 361, 5):
        longitude, latitude, _ = geod.fwd(
            radar.longitude,
            radar.latitude,
            bearing,
            radar.range_kilometres * 1000,
        )
        result.append([_rounded(longitude, 8), _rounded(latitude, 8)])
    return result


def _read_source(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise GeoreferencingError("No se pudo leer la capa de reflectividad.") from exc


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


def _parse_control_point(value: object) -> ControlPoint:
    if not isinstance(value, dict):
        raise GeoreferencingError("Cada punto de control debe ser un objeto JSON.")
    payload = cast(dict[str, object], value)
    observed = _required_mapping(payload, "observedPixel")
    return ControlPoint(
        id=_required_string(payload, "id"),
        label=_required_string(payload, "label"),
        longitude=_required_float(payload, "longitude"),
        latitude=_required_float(payload, "latitude"),
        observed=Pixel(
            x=_required_float(observed, "x"),
            y=_required_float(observed, "y"),
        ),
    )


def _required_mapping(
    payload: dict[str, object],
    key: str,
) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GeoreferencingError(f"Falta el objeto {key}.")
    return cast(dict[str, object], value)


def _required_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GeoreferencingError(f"Falta la lista {key}.")
    return cast(list[object], value)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GeoreferencingError(f"Falta el texto {key}.")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise GeoreferencingError(f"Falta el entero {key}.")
    return value


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise GeoreferencingError(f"Falta el número {key}.")
    return float(value)


def _optional_string(
    payload: dict[str, object],
    key: str,
    default: str,
) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str) or not value:
        raise GeoreferencingError(f"El campo {key} debe ser texto no vacío.")
    return value


def _rounded(value: float, digits: int) -> float:
    return round(float(value), digits)
