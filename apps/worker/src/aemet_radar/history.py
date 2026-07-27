"""Lectura defensiva del archivo de originales como historial temporal."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from aemet_radar.products import RadarProduct

TimeSource = Literal["productTime", "retrievedAt"]
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ArchivedFrame:
    product_id: str
    source_id: str
    source_provider: str | None
    source_hash: str
    product_time: datetime | None
    retrieved_at: datetime
    last_retrieved_at: datetime
    timeline_time: datetime
    time_source: TimeSource
    raw_path: Path
    raw_relative_path: str
    report_path: Path


@dataclass(frozen=True, slots=True)
class HistoryScan:
    frames: tuple[ArchivedFrame, ...]
    issues: tuple[str, ...]
    discarded_duplicates: int


def scan_product_history(data_dir: Path, product: RadarProduct) -> HistoryScan:
    """Carga informes válidos, deduplica y devuelve fotogramas ordenados."""

    resolved_data_dir = data_dir.resolve()
    product_root = resolved_data_dir / "raw" / product.id
    candidates: list[ArchivedFrame] = []
    issues: list[str] = []

    for report_path in sorted(product_root.glob("*/*/*/*.json")):
        try:
            candidates.append(_load_frame(resolved_data_dir, product, report_path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            issues.append(report_path.relative_to(resolved_data_dir).as_posix())

    by_source: dict[str, ArchivedFrame] = {}
    discarded = 0
    for frame in candidates:
        previous = by_source.get(frame.source_id)
        if previous is None or frame.last_retrieved_at > previous.last_retrieved_at:
            if previous is not None:
                discarded += 1
            by_source[frame.source_id] = frame
        else:
            discarded += 1

    by_time: dict[datetime, ArchivedFrame] = {}
    for frame in by_source.values():
        previous = by_time.get(frame.timeline_time)
        if previous is None or frame.last_retrieved_at > previous.last_retrieved_at:
            if previous is not None:
                discarded += 1
            by_time[frame.timeline_time] = frame
        else:
            discarded += 1

    frames = tuple(
        sorted(
            by_time.values(),
            key=lambda frame: (frame.timeline_time, frame.retrieved_at, frame.source_hash),
        )
    )
    return HistoryScan(
        frames=frames,
        issues=tuple(issues),
        discarded_duplicates=discarded,
    )


def _load_frame(data_dir: Path, product: RadarProduct, report_path: Path) -> ArchivedFrame:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("El informe no es un objeto JSON.")
    report = cast(dict[str, object], payload)

    product_payload = _mapping(report.get("product"))
    if _string(product_payload.get("id")) != product.id:
        raise ValueError("El informe pertenece a otro producto.")

    retrieved_at = _parse_datetime(_string(report.get("retrievedAt")))
    last_retrieved_raw = report.get("lastRetrievedAt")
    last_retrieved_at = (
        _parse_datetime(_string(last_retrieved_raw))
        if last_retrieved_raw is not None
        else retrieved_at
    )

    product_time_payload = _mapping(report.get("productTime"))
    product_time_raw = product_time_payload.get("value")
    product_time = (
        _parse_datetime(_string(product_time_raw)) if product_time_raw is not None else None
    )
    timeline_time = product_time or retrieved_at
    time_source: TimeSource = "productTime" if product_time is not None else "retrievedAt"

    image = _mapping(report.get("image"))
    source_hash = _string(image.get("sha256"))
    if _SHA256_PATTERN.fullmatch(source_hash) is None:
        raise ValueError("El informe no contiene un SHA-256 válido.")

    files = _mapping(report.get("files"))
    raw_relative_path = _string(files.get("raw"))
    raw_path = (data_dir / raw_relative_path).resolve()
    expected_root = (data_dir / "raw" / product.id).resolve()
    try:
        raw_path.relative_to(expected_root)
    except ValueError as exc:
        raise ValueError("La ruta del original sale del producto permitido.") from exc
    if raw_path.suffix.lower() not in {".gif", ".png"} or not raw_path.is_file():
        raise ValueError("El original asociado no existe o no es una imagen admitida.")

    source_payload = report.get("source")
    source_id = source_hash
    source_provider: str | None = None
    if isinstance(source_payload, dict):
        candidate = source_payload.get("observationId")
        if isinstance(candidate, str) and candidate:
            source_id = candidate
        provider = source_payload.get("provider")
        if isinstance(provider, str) and provider:
            source_provider = provider

    return ArchivedFrame(
        product_id=product.id,
        source_id=source_id,
        source_provider=source_provider,
        source_hash=source_hash,
        product_time=product_time,
        retrieved_at=retrieved_at,
        last_retrieved_at=last_retrieved_at,
        timeline_time=timeline_time,
        time_source=time_source,
        raw_path=raw_path,
        raw_relative_path=raw_path.relative_to(data_dir).as_posix(),
        report_path=report_path.resolve(),
    )


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Se esperaba un objeto JSON.")
    return cast(Mapping[str, object], value)


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Se esperaba texto no vacío.")
    return value


def parse_utc_datetime(value: str) -> datetime:
    """Interpreta una fecha ISO-8601 y la normaliza a UTC."""

    return _parse_datetime(value)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria.")
    return parsed.astimezone(UTC)
