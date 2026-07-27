"""Validación y normalización de los PNG PPI servidos por el visor de AEMET."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from aemet_radar.errors import DownloadValidationError, ViewerNoDataError
from aemet_radar.storage import atomic_write_bytes, atomic_write_json

PROCESSOR_ID = "aemet-viewer-ppi-v1"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_BACKGROUND = (239, 242, 249, 179)
_TRANSPARENT = (0, 0, 0, 0)
REFLECTIVITY_COLOURS: tuple[tuple[int, int, int, int], ...] = tuple(
    (*rgb, 255)
    for rgb in (
        (0, 0, 252),
        (0, 148, 252),
        (0, 252, 252),
        (67, 131, 35),
        (0, 192, 0),
        (0, 255, 0),
        (255, 255, 0),
        (255, 187, 0),
        (255, 127, 0),
        (255, 0, 0),
        (200, 0, 90),
    )
)
_ALLOWED_COLOURS = frozenset((_BACKGROUND, _TRANSPARENT, *REFLECTIVITY_COLOURS))


@dataclass(frozen=True, slots=True)
class ViewerPpiInspection:
    sha256: str
    size_bytes: int
    width: int
    height: int
    echo_pixels: int
    background_pixels: int
    transparent_pixels: int
    declared_content_type: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "declaredContentType": self.declared_content_type,
            "actualMimeType": "image/png",
            "format": "PNG",
            "dimensions": {"width": self.width, "height": self.height},
            "mode": "RGBA",
            "frameCount": 1,
            "ppi": {
                "echoPixels": self.echo_pixels,
                "backgroundPixels": self.background_pixels,
                "transparentPixels": self.transparent_pixels,
                "palette": [list(colour[:3]) for colour in REFLECTIVITY_COLOURS],
            },
        }

    def summary(self) -> dict[str, object]:
        return {
            "actualMimeType": "image/png",
            "format": "PNG",
            "dimensions": {"width": self.width, "height": self.height},
            "mode": "RGBA",
            "frameCount": 1,
            "reflectivityPixels": self.echo_pixels,
        }


def inspect_viewer_png(
    content: bytes,
    declared_content_type: str | None,
) -> ViewerPpiInspection:
    """Acepta únicamente el contrato RGBA del PPI, incluido un radar realmente seco."""

    digest = hashlib.sha256(content).hexdigest()
    normalized_type = (
        declared_content_type.split(";", 1)[0].strip().lower()
        if declared_content_type is not None
        else None
    )
    if not content.startswith(_PNG_SIGNATURE) or normalized_type not in {None, "image/png"}:
        raise DownloadValidationError(
            "El recurso descargado no es un PNG PPI válido.",
            size_bytes=len(content),
            sha256=digest,
            declared_content_type=normalized_type,
        )
    try:
        with Image.open(BytesIO(content)) as source:
            if source.format != "PNG" or source.mode != "RGBA":
                raise ViewerNoDataError("AEMET no publicó un PPI RGBA utilizable.")
            width, height = source.size
            if not 1_000 <= width <= 5_000 or not 1_000 <= height <= 5_000:
                raise ViewerNoDataError("AEMET no publicó un PPI con geometría válida.")
            source.load()
            colours = source.getcolors(maxcolors=64)
    except ViewerNoDataError:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as exc:
        raise DownloadValidationError(
            "El recurso descargado no es un PNG PPI válido.",
            size_bytes=len(content),
            sha256=digest,
            declared_content_type=normalized_type,
        ) from exc

    if colours is None:
        raise ViewerNoDataError("La imagen de AEMET no cumple la paleta PPI publicada.")
    observed = {colour for _count, colour in colours}
    if not observed.issubset(_ALLOWED_COLOURS):
        raise ViewerNoDataError("La imagen de AEMET no contiene un PPI utilizable.")
    counts = {colour: count for count, colour in colours}
    echo_pixels = sum(counts.get(colour, 0) for colour in REFLECTIVITY_COLOURS)
    return ViewerPpiInspection(
        sha256=digest,
        size_bytes=len(content),
        width=width,
        height=height,
        echo_pixels=echo_pixels,
        background_pixels=counts.get(_BACKGROUND, 0),
        transparent_pixels=counts.get(_TRANSPARENT, 0),
        declared_content_type=normalized_type,
    )


def publish_viewer_overlay(
    source_path: Path,
    *,
    output_dir: Path,
    expected_sha256: str,
    coordinates: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
) -> dict[str, object]:
    """Elimina fondo y no-dato; conserva exactamente los ecos PPI oficiales."""

    content = source_path.read_bytes()
    inspection = inspect_viewer_png(content, "image/png")
    if inspection.sha256 != expected_sha256:
        raise DownloadValidationError(
            "El PNG PPI no coincide con el hash archivado.",
            size_bytes=len(content),
            sha256=inspection.sha256,
            declared_content_type="image/png",
        )
    with Image.open(BytesIO(content)) as source:
        rgba = source.convert("RGBA")
        alpha = rgba.getchannel("A").point(lambda value: 255 if value == 255 else 0)
        rgba.putalpha(alpha)
        output = BytesIO()
        rgba.save(output, format="PNG", optimize=True)

    image_path = output_dir / "overlay.png"
    report_path = output_dir / "viewer-processing.json"
    atomic_write_bytes(image_path, output.getvalue())
    report: dict[str, object] = {
        "schemaVersion": 1,
        "processor": PROCESSOR_ID,
        "source": {
            "sha256": f"sha256:{inspection.sha256}",
            "width": inspection.width,
            "height": inspection.height,
        },
        "statistics": {
            "reflectivityPixels": inspection.echo_pixels,
            "backgroundPixelsRemoved": inspection.background_pixels,
            "transparentPixels": inspection.transparent_pixels,
        },
        "output": {
            "file": image_path.name,
            "maplibreCoordinates": [list(coordinate) for coordinate in coordinates],
        },
    }
    atomic_write_json(report_path, report)
    return report
