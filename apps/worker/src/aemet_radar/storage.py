"""Archivo de originales e informes mediante operaciones atómicas."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from aemet_radar.products import RadarProduct


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    status: Literal["stored", "duplicate"]
    raw_path: Path
    report_path: Path


class ArchiveStore:
    """Almacena un único original por hash y producto."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()

    def archive(
        self,
        *,
        product: RadarProduct,
        content: bytes,
        sha256: str,
        retrieved_at: datetime,
        report: dict[str, object],
        extension: str = ".gif",
        archive_key: str | None = None,
    ) -> ArchiveResult:
        if not re.fullmatch(r"\.[a-z0-9]+", extension):
            raise ValueError("La extensión de archivo no es segura.")
        key = archive_key or sha256
        if not re.fullmatch(r"[A-Za-z0-9._-]+", key):
            raise ValueError("La clave de archivo no es segura.")
        product_root = self.data_dir / "raw" / product.id
        existing = next(product_root.glob(f"*/*/*/{key}{extension}"), None)
        if existing is not None:
            existing_report = existing.with_suffix(".json")
            refreshed = _merge_duplicate_report(
                report=report,
                existing_report=existing_report,
                data_dir=self.data_dir,
                raw_path=existing,
            )
            atomic_write_json(existing_report, refreshed)
            return ArchiveResult(
                status="duplicate",
                raw_path=existing,
                report_path=existing_report,
            )

        target_dir = (
            product_root
            / f"{retrieved_at.year:04d}"
            / f"{retrieved_at.month:02d}"
            / f"{retrieved_at.day:02d}"
        )
        raw_path = target_dir / f"{key}{extension}"
        report_path = target_dir / f"{key}.json"
        target_dir.mkdir(parents=True, exist_ok=True)

        complete_report = _report_with_paths(report, self.data_dir, raw_path, report_path)
        atomic_write_bytes(raw_path, content)
        atomic_write_json(report_path, complete_report)
        return ArchiveResult(status="stored", raw_path=raw_path, report_path=report_path)

    def write_comparison(
        self,
        *,
        generated_at: datetime,
        products: list[dict[str, object]],
    ) -> Path:
        target_dir = self.data_dir / "reports" / "phase-1"
        filename = generated_at.strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        path = target_dir / filename
        atomic_write_json(
            path,
            {
                "schemaVersion": 1,
                "generatedAt": generated_at.isoformat().replace("+00:00", "Z"),
                "products": products,
            },
        )
        return path

    def write_inventory(
        self,
        *,
        generated_at: datetime,
        products: list[dict[str, object]],
    ) -> Path:
        target_dir = self.data_dir / "reports" / "phase-1"
        filename = "inventory-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        path = target_dir / filename
        atomic_write_json(
            path,
            {
                "schemaVersion": 1,
                "generatedAt": generated_at.isoformat().replace("+00:00", "Z"),
                "probe": "gateway-only",
                "products": products,
            },
        )
        return path


def _report_with_paths(
    report: dict[str, object],
    data_dir: Path,
    raw_path: Path,
    report_path: Path,
) -> dict[str, object]:
    return {
        **report,
        "files": {
            "raw": raw_path.relative_to(data_dir).as_posix(),
            "report": report_path.relative_to(data_dir).as_posix(),
        },
    }


def _merge_duplicate_report(
    *,
    report: dict[str, object],
    existing_report: Path,
    data_dir: Path,
    raw_path: Path,
) -> dict[str, object]:
    refreshed = _report_with_paths(report, data_dir, raw_path, existing_report)
    previous: dict[str, object] = {}
    if existing_report.exists():
        try:
            loaded = json.loads(existing_report.read_text())
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict):
            previous = cast(dict[str, object], loaded)

    first_retrieved_at = previous.get("retrievedAt", refreshed.get("retrievedAt"))
    last_retrieved_at = refreshed.get("retrievedAt")
    previous_count = previous.get("duplicateCount", 0)
    duplicate_count = previous_count + 1 if isinstance(previous_count, int) else 1
    return {
        **refreshed,
        "retrievedAt": first_retrieved_at,
        "lastRetrievedAt": last_retrieved_at,
        "duplicateCount": duplicate_count,
    }


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Publica bytes mediante escritura temporal y reemplazo en el mismo directorio."""

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Serializa y publica un objeto JSON de forma atómica."""

    serialized = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    atomic_write_bytes(path, serialized)
