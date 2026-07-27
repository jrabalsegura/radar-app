"""Descubrimiento reproducible de muestras para máscaras regionales."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast


@dataclass(frozen=True, slots=True)
class MaskSample:
    path: Path
    sha256: str
    retrieved_at: datetime | None


@dataclass(frozen=True, slots=True)
class MaskSampleInventory:
    product_id: str
    samples: tuple[MaskSample, ...]

    @property
    def span_hours(self) -> float | None:
        observations = [
            sample.retrieved_at for sample in self.samples if sample.retrieved_at is not None
        ]
        if len(observations) != len(self.samples) or len(observations) < 2:
            return None
        return (max(observations) - min(observations)).total_seconds() / 3600

    @property
    def source_evidence(self) -> dict[str, str]:
        return {
            sample.sha256: _format_timestamp(sample.retrieved_at)
            for sample in self.samples
            if sample.retrieved_at is not None
        }


def discover_mask_samples(
    product_id: str,
    sample_roots: tuple[Path, ...],
) -> MaskSampleInventory:
    """Localiza originales archivados, deduplicados por contenido."""

    distinct: dict[str, MaskSample] = {}
    for root in sample_roots:
        product_root = root.resolve() / "raw" / product_id
        for path in sorted(product_root.glob("*/*/*/*.gif")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            candidate = MaskSample(
                path=path,
                sha256=digest,
                retrieved_at=_read_retrieved_at(path.with_suffix(".json")),
            )
            previous = distinct.get(digest)
            if previous is None or _is_earlier(candidate.retrieved_at, previous.retrieved_at):
                distinct[digest] = candidate
    return MaskSampleInventory(
        product_id=product_id,
        samples=tuple(distinct[digest] for digest in sorted(distinct)),
    )


def _read_retrieved_at(path: Path) -> datetime | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = cast(dict[str, object], payload).get("retrievedAt")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _is_earlier(candidate: datetime | None, previous: datetime | None) -> bool:
    if candidate is None:
        return False
    return previous is None or candidate < previous


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        raise ValueError("No se puede serializar una observación sin fecha.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
