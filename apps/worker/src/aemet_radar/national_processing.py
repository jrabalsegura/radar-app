"""Máscara, paleta y georreferenciación de la composición nacional."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image, UnidentifiedImageError

from aemet_radar.errors import (
    DownloadValidationError,
    ReflectivityProcessingError,
    ViewerNoDataError,
)
from aemet_radar.storage import atomic_write_bytes, atomic_write_json
from aemet_radar.viewer_client import MapCoordinates

PROCESSOR_ID = "national-v1"
DEFAULT_PALETTE_CONFIG = Path("config/palettes/national-v1.json")
DEFAULT_MASK_CONFIG = Path("config/masks/national-v1.json")
DEFAULT_GEOREFERENCING_CONFIG = Path("config/georeferencing/national-v1.json")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

Rgb = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class NationalProcessingConfig:
    width: int
    height: int
    bit_depth: int
    source_alpha: int
    no_data_rgb: frozenset[Rgb]
    reflectivity_rgb: frozenset[Rgb]
    expected_coordinates: MapCoordinates
    coordinate_tolerance: float
    palette_sha256: str
    mask_sha256: str
    georeferencing_sha256: str


@dataclass(frozen=True, slots=True)
class NationalInspection:
    sha256: str
    size_bytes: int
    width: int
    height: int
    bit_depth: int
    reflectivity_pixels: int
    no_data_pixels: int
    transparent_pixels: int
    observed_reflectivity_rgb: tuple[Rgb, ...]
    declared_content_type: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "declaredContentType": self.declared_content_type,
            "actualMimeType": "image/png",
            "format": "PNG",
            "dimensions": {"width": self.width, "height": self.height},
            "mode": "P",
            "bitDepth": self.bit_depth,
            "frameCount": 1,
            "national": {
                "reflectivityPixels": self.reflectivity_pixels,
                "noDataPixels": self.no_data_pixels,
                "transparentPixels": self.transparent_pixels,
                "observedReflectivityRgb": [
                    list(colour) for colour in self.observed_reflectivity_rgb
                ],
            },
        }

    def summary(self) -> dict[str, object]:
        return {
            "actualMimeType": "image/png",
            "format": "PNG",
            "dimensions": {"width": self.width, "height": self.height},
            "mode": "P",
            "bitDepth": self.bit_depth,
            "frameCount": 1,
            "reflectivityPixels": self.reflectivity_pixels,
        }


def inspect_national_png(
    content: bytes,
    declared_content_type: str | None,
    *,
    configuration: NationalProcessingConfig | None = None,
    palette_path: Path = DEFAULT_PALETTE_CONFIG,
    mask_path: Path = DEFAULT_MASK_CONFIG,
    georeferencing_path: Path = DEFAULT_GEOREFERENCING_CONFIG,
) -> NationalInspection:
    """Acepta solo el PNG indexado nacional y distingue láminas de indisponibilidad."""

    config = configuration or load_national_config(
        palette_path=palette_path,
        mask_path=mask_path,
        georeferencing_path=georeferencing_path,
    )
    digest = hashlib.sha256(content).hexdigest()
    normalized_type = (
        declared_content_type.split(";", 1)[0].strip().lower()
        if declared_content_type is not None
        else None
    )
    if not content.startswith(_PNG_SIGNATURE) or normalized_type not in {
        None,
        "image/png",
    }:
        raise DownloadValidationError(
            "El recurso descargado no es un PNG nacional válido.",
            size_bytes=len(content),
            sha256=digest,
            declared_content_type=normalized_type,
        )
    bit_depth = _png_bit_depth(content)
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format != "PNG" or source.mode != "P":
                raise ViewerNoDataError(
                    "AEMET no publicó una composición nacional indexada utilizable."
                )
            if source.size != (config.width, config.height):
                raise ViewerNoDataError("La composición nacional no tiene la geometría validada.")
            if bit_depth != config.bit_depth:
                raise ViewerNoDataError("La composición nacional no tiene la profundidad validada.")
            source.load()
            colour_counts = source.getcolors(maxcolors=256)
            if colour_counts is None:
                raise ViewerNoDataError("La composición nacional supera la paleta validada.")
            raw_palette = source.getpalette()
            if raw_palette is None:
                raise ViewerNoDataError(
                    "La composición nacional no contiene una paleta utilizable."
                )
            indexed_colours = cast(list[tuple[int, int]], colour_counts)
            palette = raw_palette
            transparency = source.info.get("transparency")
            entries = {
                index: (
                    tuple(palette[index * 3 : index * 3 + 3]),
                    _palette_alpha(transparency, index),
                    count,
                )
                for count, index in indexed_colours
            }
    except ViewerNoDataError:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as exc:
        raise DownloadValidationError(
            "El recurso descargado no es un PNG nacional válido.",
            size_bytes=len(content),
            sha256=digest,
            declared_content_type=normalized_type,
        ) from exc

    reflectivity_pixels = 0
    no_data_pixels = 0
    transparent_pixels = 0
    observed_reflectivity: set[Rgb] = set()
    for rgb_value, alpha, count in entries.values():
        rgb = cast(Rgb, rgb_value)
        if rgb in config.reflectivity_rgb and alpha == config.source_alpha:
            reflectivity_pixels += count
            observed_reflectivity.add(rgb)
        elif rgb == (255, 255, 255) and alpha == 0:
            transparent_pixels += count
        elif rgb in config.no_data_rgb and alpha == config.source_alpha:
            no_data_pixels += count
        else:
            raise ViewerNoDataError(
                "La imagen de AEMET no contiene una composición nacional utilizable."
            )

    return NationalInspection(
        sha256=digest,
        size_bytes=len(content),
        width=config.width,
        height=config.height,
        bit_depth=bit_depth,
        reflectivity_pixels=reflectivity_pixels,
        no_data_pixels=no_data_pixels,
        transparent_pixels=transparent_pixels,
        observed_reflectivity_rgb=tuple(sorted(observed_reflectivity)),
        declared_content_type=normalized_type,
    )


def publish_national_overlay(
    source_path: Path,
    *,
    output_dir: Path,
    expected_sha256: str,
    coordinates: MapCoordinates,
    palette_path: Path = DEFAULT_PALETTE_CONFIG,
    mask_path: Path = DEFAULT_MASK_CONFIG,
    georeferencing_path: Path = DEFAULT_GEOREFERENCING_CONFIG,
) -> dict[str, object]:
    """Genera una máscara binaria por fotograma y un overlay RGBA sin fondo."""

    config = load_national_config(
        palette_path=palette_path,
        mask_path=mask_path,
        georeferencing_path=georeferencing_path,
    )
    _validate_coordinates(coordinates, config)
    content = source_path.read_bytes()
    inspection = inspect_national_png(
        content,
        "image/png",
        configuration=config,
    )
    if inspection.sha256 != expected_sha256:
        raise DownloadValidationError(
            "El PNG nacional no coincide con el hash archivado.",
            size_bytes=len(content),
            sha256=inspection.sha256,
            declared_content_type="image/png",
        )

    with Image.open(BytesIO(content)) as source:
        source.info.pop("transparency", None)
        rgb = source.convert("RGB")
    mask = Image.new("L", rgb.size)
    mask.putdata(
        [
            255 if cast(Rgb, pixel) in config.reflectivity_rgb else 0
            for pixel in rgb.get_flattened_data()
        ]
    )
    overlay = rgb.convert("RGBA")
    overlay.putalpha(mask)

    mask_buffer = BytesIO()
    mask.save(mask_buffer, format="PNG", optimize=True)
    overlay_buffer = BytesIO()
    overlay.save(overlay_buffer, format="PNG", optimize=True)
    mask_output_path = output_dir / "mask.png"
    overlay_path = output_dir / "overlay.png"
    report_path = output_dir / "national-processing.json"
    atomic_write_bytes(mask_output_path, mask_buffer.getvalue())
    atomic_write_bytes(overlay_path, overlay_buffer.getvalue())
    report: dict[str, object] = {
        "schemaVersion": 1,
        "processor": PROCESSOR_ID,
        "source": {
            "sha256": f"sha256:{inspection.sha256}",
            "width": inspection.width,
            "height": inspection.height,
            "bitDepth": inspection.bit_depth,
        },
        "configuration": {
            "paletteSha256": f"sha256:{config.palette_sha256}",
            "maskSha256": f"sha256:{config.mask_sha256}",
            "georeferencingSha256": f"sha256:{config.georeferencing_sha256}",
        },
        "mask": {
            "algorithm": "exact-reflectivity-palette-v1",
            "file": mask_output_path.name,
            "reflectivityPixels": inspection.reflectivity_pixels,
            "discardedPixels": (inspection.no_data_pixels + inspection.transparent_pixels),
        },
        "output": {
            "file": overlay_path.name,
            "maplibreCoordinates": [list(coordinate) for coordinate in coordinates],
        },
    }
    atomic_write_json(report_path, report)
    return report


def load_national_config(
    *,
    palette_path: Path = DEFAULT_PALETTE_CONFIG,
    mask_path: Path = DEFAULT_MASK_CONFIG,
    georeferencing_path: Path = DEFAULT_GEOREFERENCING_CONFIG,
) -> NationalProcessingConfig:
    palette_bytes, palette = _load_config_file(palette_path)
    mask_bytes, mask = _load_config_file(mask_path)
    georeferencing_bytes, georeferencing = _load_config_file(georeferencing_path)
    for payload in (palette, mask, georeferencing):
        if (
            payload.get("schemaVersion") != 1
            or payload.get("productId") != "national"
            or payload.get("processor") != PROCESSOR_ID
        ):
            raise ReflectivityProcessingError(
                "La configuración nacional no cumple el contrato versionado."
            )

    source = _mapping(palette.get("source"))
    expected_coordinates = _coordinates(georeferencing.get("expectedMaplibreCoordinates"))
    return NationalProcessingConfig(
        width=_positive_integer(source.get("width")),
        height=_positive_integer(source.get("height")),
        bit_depth=_positive_integer(source.get("bitDepth")),
        source_alpha=_alpha(source.get("alpha")),
        no_data_rgb=_rgb_set(palette.get("noDataRgb")),
        reflectivity_rgb=_rgb_set(palette.get("reflectivityRgb")),
        expected_coordinates=expected_coordinates,
        coordinate_tolerance=_positive_number(georeferencing.get("coordinateToleranceDegrees")),
        palette_sha256=hashlib.sha256(palette_bytes).hexdigest(),
        mask_sha256=hashlib.sha256(mask_bytes).hexdigest(),
        georeferencing_sha256=hashlib.sha256(georeferencing_bytes).hexdigest(),
    )


def _validate_coordinates(
    coordinates: MapCoordinates,
    config: NationalProcessingConfig,
) -> None:
    tolerance = config.coordinate_tolerance
    if any(
        abs(observed_component - expected_component) > tolerance
        for observed, expected in zip(coordinates, config.expected_coordinates, strict=True)
        for observed_component, expected_component in zip(observed, expected, strict=True)
    ):
        raise ReflectivityProcessingError(
            "Los límites nacionales no coinciden con la georreferenciación validada."
        )


def _load_config_file(path: Path) -> tuple[bytes, dict[str, object]]:
    try:
        content = path.resolve().read_bytes()
        payload = json.loads(content)
    except (OSError, ValueError) as exc:
        raise ReflectivityProcessingError("No se pudo leer una configuración nacional.") from exc
    if not isinstance(payload, dict):
        raise ReflectivityProcessingError("La configuración nacional debe ser un objeto JSON.")
    return content, cast(dict[str, object], payload)


def _png_bit_depth(content: bytes) -> int:
    if len(content) < 29 or content[12:16] != b"IHDR":
        raise ViewerNoDataError("El PNG nacional no contiene una cabecera IHDR.")
    return content[24]


def _palette_alpha(transparency: object, index: int) -> int:
    if isinstance(transparency, bytes):
        return transparency[index] if index < len(transparency) else 255
    if isinstance(transparency, int):
        return 0 if index == transparency else 255
    return 255


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReflectivityProcessingError("La configuración nacional contiene un bloque no válido.")
    return cast(dict[str, object], value)


def _rgb_set(value: object) -> frozenset[Rgb]:
    if not isinstance(value, list) or not value:
        raise ReflectivityProcessingError("La configuración nacional no contiene una paleta.")
    result: set[Rgb] = set()
    for row in value:
        if (
            not isinstance(row, list)
            or len(row) != 3
            or not all(
                isinstance(component, int)
                and not isinstance(component, bool)
                and 0 <= component <= 255
                for component in row
            )
        ):
            raise ReflectivityProcessingError("La paleta nacional contiene un RGB no válido.")
        result.add(cast(Rgb, tuple(row)))
    return frozenset(result)


def _coordinates(value: object) -> MapCoordinates:
    if not isinstance(value, list) or len(value) != 4:
        raise ReflectivityProcessingError(
            "La georreferenciación nacional no contiene cuatro esquinas."
        )
    result: list[tuple[float, float]] = []
    for row in value:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not all(
                isinstance(component, (int, float)) and not isinstance(component, bool)
                for component in row
            )
        ):
            raise ReflectivityProcessingError(
                "La georreferenciación nacional contiene una coordenada no válida."
            )
        result.append((float(row[0]), float(row[1])))
    return cast(MapCoordinates, tuple(result))


def _positive_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReflectivityProcessingError("La configuración nacional requiere un entero positivo.")
    return value


def _alpha(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
        raise ReflectivityProcessingError("La configuración nacional contiene un alfa no válido.")
    return value


def _positive_number(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ReflectivityProcessingError("La configuración nacional requiere un número positivo.")
    return float(value)
