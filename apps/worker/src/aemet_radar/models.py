"""Modelos internos de la ingesta de originales."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from aemet_radar.products import RadarProduct


@dataclass(frozen=True, slots=True)
class MetadataDownload:
    status: Literal["ok", "error", "missing"]
    headers: dict[str, str]
    payload: object | None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadedProduct:
    product: RadarProduct
    content: bytes
    retrieved_at: datetime
    resource_name: str
    gateway_status: int
    gateway_headers: dict[str, str]
    data_status: int
    data_headers: dict[str, str]
    metadata: MetadataDownload


@dataclass(frozen=True, slots=True)
class ProductProbe:
    product_id: str
    label: str
    aemet_code: str | None
    status: Literal["available", "unavailable"]
    http_status: int
    api_status: int
    has_data_url: bool
    has_metadata_url: bool
    headers: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "productId": self.product_id,
            "label": self.label,
            "aemetCode": self.aemet_code,
            "status": self.status,
            "httpStatus": self.http_status,
            "apiStatus": self.api_status,
            "hasDataUrl": self.has_data_url,
            "hasMetadataUrl": self.has_metadata_url,
            "headers": self.headers,
        }


@dataclass(frozen=True, slots=True)
class ProductTimeResult:
    status: Literal["candidate", "unresolved"]
    value: str | None
    source: str | None
    confidence: Literal["medium", "low", "none"]
    evidence: tuple[dict[str, object], ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ImageInspection:
    sha256: str
    size_bytes: int
    declared_content_type: str | None
    actual_mime_type: str
    format: str
    width: int
    height: int
    mode: str
    frame_count: int
    palette_mode: str | None
    palette_entries: tuple[tuple[int, int, int], ...]
    used_palette_indexes: tuple[int, ...]
    internal_metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "declaredContentType": self.declared_content_type,
            "actualMimeType": self.actual_mime_type,
            "format": self.format,
            "dimensions": {"width": self.width, "height": self.height},
            "mode": self.mode,
            "frameCount": self.frame_count,
            "palette": {
                "present": bool(self.palette_entries),
                "mode": self.palette_mode,
                "colorCount": len(self.palette_entries),
                "entries": [list(entry) for entry in self.palette_entries],
                "usedIndexes": list(self.used_palette_indexes),
            },
            "internalMetadata": self.internal_metadata,
        }

    def summary(self) -> dict[str, object]:
        return {
            "actualMimeType": self.actual_mime_type,
            "format": self.format,
            "dimensions": {"width": self.width, "height": self.height},
            "mode": self.mode,
            "frameCount": self.frame_count,
            "paletteColorCount": len(self.palette_entries),
        }


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    product_id: str
    status: Literal["stored", "duplicate"]
    sha256: str
    raw_path: Path
    report_path: Path
    retrieved_at: datetime
    inspection: dict[str, object]
    product_time: ProductTimeResult

    def to_dict(self, *, relative_to: Path | None = None) -> dict[str, object]:
        raw_path = self.raw_path
        report_path = self.report_path
        if relative_to is not None:
            raw_path = raw_path.relative_to(relative_to)
            report_path = report_path.relative_to(relative_to)
        return {
            "productId": self.product_id,
            "status": self.status,
            "sha256": self.sha256,
            "rawFile": raw_path.as_posix(),
            "reportFile": report_path.as_posix(),
            "retrievedAt": self.retrieved_at.isoformat().replace("+00:00", "Z"),
            "inspection": self.inspection,
            "productTime": self.product_time.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class BatchFetchOutcome:
    """Resultado resumido de una línea temporal obtenida del visor oficial."""

    product_id: str
    status: Literal["stored", "duplicate"]
    source: Literal["aemet-viewer"]
    stored_frames: int
    duplicate_frames: int
    skipped_frames: int
    latest_observation: datetime

    def to_dict(self, *, relative_to: Path | None = None) -> dict[str, object]:
        del relative_to
        return {
            "productId": self.product_id,
            "status": self.status,
            "source": self.source,
            "storedFrames": self.stored_frames,
            "duplicateFrames": self.duplicate_frames,
            "skippedFrames": self.skipped_frames,
            "latestObservation": (self.latest_observation.isoformat().replace("+00:00", "Z")),
        }
