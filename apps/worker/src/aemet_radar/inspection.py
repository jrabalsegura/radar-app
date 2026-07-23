"""Inspección determinista de GIF y búsqueda no-OCR de la hora de producto."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from aemet_radar.errors import DownloadValidationError
from aemet_radar.models import ImageInspection, ProductTimeResult

_MAX_DIMENSION = 10_000
_MAX_METADATA_TEXT_LENGTH = 2_048
_TIMESTAMP_PATTERNS = (
    (re.compile(r"(?<!\d)(\d{8})[T_-]?(\d{6})Z?(?!\d)"), "%Y%m%d%H%M%S"),
    (re.compile(r"(?<!\d)(\d{8})[T_-]?(\d{4})Z?(?!\d)"), "%Y%m%d%H%M"),
    (
        re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})[T _](\d{2}:\d{2}:\d{2})Z?(?!\d)"),
        "%Y-%m-%d%H:%M:%S",
    ),
)


def inspect_gif(content: bytes, declared_content_type: str | None) -> ImageInspection:
    """Valida un GIF y devuelve sus propiedades sin modificarlo."""

    if not content:
        raise DownloadValidationError("El recurso descargado está vacío.")

    digest = hashlib.sha256(content).hexdigest()
    normalized_content_type = _normalize_content_type(declared_content_type)

    try:
        with Image.open(BytesIO(content)) as candidate:
            detected_format = candidate.format
            candidate.verify()
        with Image.open(BytesIO(content)) as image:
            image.load()
            if detected_format != "GIF" or image.format != "GIF":
                raise DownloadValidationError("El recurso descargado no es un GIF.")
            width, height = image.size
            if width <= 0 or height <= 0 or width > _MAX_DIMENSION or height > _MAX_DIMENSION:
                raise DownloadValidationError("Las dimensiones del GIF no son aceptables.")

            palette_entries = _palette_entries(image)
            used_indexes = _used_palette_indexes(image)
            internal_metadata = {
                str(key): _json_safe(value) for key, value in sorted(image.info.items())
            }
            return ImageInspection(
                sha256=digest,
                size_bytes=len(content),
                declared_content_type=normalized_content_type,
                actual_mime_type="image/gif",
                format="GIF",
                width=width,
                height=height,
                mode=image.mode,
                frame_count=getattr(image, "n_frames", 1),
                palette_mode=image.palette.mode if image.palette is not None else None,
                palette_entries=palette_entries,
                used_palette_indexes=used_indexes,
                internal_metadata=internal_metadata,
            )
    except DownloadValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise DownloadValidationError("El recurso descargado no es un GIF válido.") from exc


def resolve_product_time(
    *,
    headers: Mapping[str, str],
    internal_metadata: Mapping[str, object],
    resource_name: str,
    retrieved_at: datetime,
    cadence_minutes: int,
) -> ProductTimeResult:
    """Busca evidencias de hora sin afirmar una precisión que no está demostrada."""

    evidence: list[dict[str, object]] = []

    last_modified = headers.get("last-modified")
    if last_modified is not None:
        parsed = _parse_http_datetime(last_modified)
        evidence.append(
            {
                "source": "http:last-modified",
                "raw": last_modified,
                "value": _isoformat(parsed) if parsed is not None else None,
            }
        )
        if parsed is not None:
            return ProductTimeResult(
                status="candidate",
                value=_isoformat(parsed),
                source="http:last-modified",
                confidence="medium",
                evidence=tuple(evidence),
                notes=(
                    "Last-Modified es una candidata; una muestra real debe confirmar "
                    "si coincide con la hora impresa del producto.",
                ),
            )

    metadata_candidate = _first_timestamp(_metadata_text_values(internal_metadata))
    if metadata_candidate is not None:
        evidence.append(
            {
                "source": "gif:metadata",
                "value": _isoformat(metadata_candidate),
            }
        )
        return ProductTimeResult(
            status="candidate",
            value=_isoformat(metadata_candidate),
            source="gif:metadata",
            confidence="medium",
            evidence=tuple(evidence),
            notes=("La candidata procede de texto interno del GIF y debe validarse visualmente.",),
        )

    resource_candidate = _first_timestamp((resource_name,))
    if resource_candidate is not None:
        evidence.append(
            {
                "source": "resource:name",
                "value": _isoformat(resource_candidate),
            }
        )
        return ProductTimeResult(
            status="candidate",
            value=_isoformat(resource_candidate),
            source="resource:name",
            confidence="low",
            evidence=tuple(evidence),
            notes=("El nombre del recurso es efímero; esta candidata requiere confirmación.",),
        )

    evidence.append(
        {
            "source": "retrieval",
            "value": _isoformat(retrieved_at),
            "cadenceMinutes": cadence_minutes,
        }
    )
    return ProductTimeResult(
        status="unresolved",
        value=None,
        source=None,
        confidence="none",
        evidence=tuple(evidence),
        notes=(
            "No se inventa productTime a partir de la cadencia.",
            "retrievedAt queda disponible como referencia distinta de la hora del producto.",
        ),
    )


def _normalize_content_type(value: str | None) -> str | None:
    if value is None:
        return None
    return value.partition(";")[0].strip().lower() or None


def _palette_entries(image: Image.Image) -> tuple[tuple[int, int, int], ...]:
    palette = image.getpalette()
    if palette is None:
        return ()
    components = 3
    usable_length = len(palette) - (len(palette) % components)
    return tuple(
        (palette[index], palette[index + 1], palette[index + 2])
        for index in range(0, usable_length, components)
    )


def _used_palette_indexes(image: Image.Image) -> tuple[int, ...]:
    if image.mode != "P":
        return ()
    histogram = image.histogram()
    return tuple(index for index, count in enumerate(histogram[:256]) if count)


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str):
            return value[:_MAX_METADATA_TEXT_LENGTH]
        return value
    if isinstance(value, bytes):
        return value[:_MAX_METADATA_TEXT_LENGTH].decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in list(value.items())[:256]}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value[:256]]
    return str(value)[:_MAX_METADATA_TEXT_LENGTH]


def _parse_http_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _metadata_text_values(metadata: Mapping[str, object]) -> Iterable[str]:
    for key, value in metadata.items():
        yield key
        yield from _text_values(value)


def _text_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _text_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _text_values(item)


def _first_timestamp(values: Iterable[str]) -> datetime | None:
    for value in values:
        for pattern, date_format in _TIMESTAMP_PATTERNS:
            match = pattern.search(value)
            if match is None:
                continue
            compact = "".join(match.groups())
            try:
                return datetime.strptime(compact, date_format).replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
