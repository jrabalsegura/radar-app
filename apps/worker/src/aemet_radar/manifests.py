"""Construcción y publicación atómica de manifiestos de originales."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.parse import quote

from aemet_radar.history import (
    ArchivedFrame,
    HistoryScan,
    isoformat_utc,
    scan_product_history,
)
from aemet_radar.products import RadarProduct
from aemet_radar.storage import atomic_write_json

_GAP_JITTER_TOLERANCE_SECONDS = 1.0
MapCoordinates = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]


@dataclass(frozen=True, slots=True)
class FrameImage:
    url: str
    coordinates: MapCoordinates


@dataclass(frozen=True, slots=True)
class ManifestResult:
    product_id: str
    path: Path
    payload: dict[str, object]
    scan: HistoryScan


class ManifestPublisher:
    """Publica el historial visible bajo el árbol estático de ``data``."""

    def __init__(
        self,
        data_dir: Path,
        *,
        history_hours: float = 3.0,
        image_resolver: Callable[[RadarProduct, ArchivedFrame], FrameImage | None] | None = None,
        radar_metadata_resolver: Callable[[RadarProduct], dict[str, object]] | None = None,
    ) -> None:
        if history_hours <= 0:
            raise ValueError("history_hours debe ser mayor que cero.")
        self.data_dir = data_dir.resolve()
        self.history_hours = history_hours
        self.image_resolver = image_resolver
        self.radar_metadata_resolver = radar_metadata_resolver

    def rebuild_product(
        self,
        product: RadarProduct,
        *,
        generated_at: datetime,
    ) -> ManifestResult:
        scan = scan_product_history(self.data_dir, product)
        payload = build_product_manifest(
            product,
            scan,
            generated_at=generated_at,
            history_hours=self.history_hours,
            image_resolver=self.image_resolver,
        )
        path = self.manifest_path(product)
        atomic_write_json(path, payload)
        return ManifestResult(
            product_id=product.id,
            path=path,
            payload=payload,
            scan=scan,
        )

    def rebuild_index(
        self,
        products: tuple[RadarProduct, ...],
        *,
        generated_at: datetime,
    ) -> Path:
        radars: list[dict[str, object]] = []
        for product in products:
            manifest_path = self.manifest_path(product)
            manifest = _load_json_object(manifest_path)
            metadata = (
                self.radar_metadata_resolver(product)
                if self.radar_metadata_resolver is not None
                else {}
            )
            radars.append(
                {
                    "id": product.id,
                    "label": product.label,
                    "kind": product.kind.value,
                    "cadenceMinutes": product.cadence_minutes,
                    "manifestUrl": f"/radar/{quote(product.id)}/manifest.json",
                    "available": manifest is not None and bool(manifest.get("frames")),
                    "latestFrameTime": (
                        manifest.get("latestFrameTime") if manifest is not None else None
                    ),
                    **metadata,
                }
            )

        path = self.data_dir / "radar" / "index.json"
        atomic_write_json(
            path,
            {
                "schemaVersion": 1,
                "generatedAt": isoformat_utc(generated_at),
                "radars": radars,
            },
        )
        return path

    def manifest_path(self, product: RadarProduct) -> Path:
        return self.data_dir / "radar" / product.id / "manifest.json"

    def read_product(self, product: RadarProduct) -> dict[str, object] | None:
        return _load_json_object(self.manifest_path(product))


def build_product_manifest(
    product: RadarProduct,
    scan: HistoryScan,
    *,
    generated_at: datetime,
    history_hours: float,
    image_resolver: Callable[[RadarProduct, ArchivedFrame], FrameImage | None] | None = None,
) -> dict[str, object]:
    frames = scan.frames
    selected: tuple[ArchivedFrame, ...] = ()
    window_start: datetime | None = None
    window_end: datetime | None = None

    if frames:
        window_end = frames[-1].timeline_time
        window_start = window_end - timedelta(hours=history_hours)
        selected = select_history_frames(frames, history_hours)

    public_frames = [
        _public_frame(frame, product, image_resolver=image_resolver) for frame in selected
    ]
    product_times = [frame.product_time for frame in selected if frame.product_time is not None]
    latest_product_time = max(product_times) if product_times else None
    return {
        "schemaVersion": 1,
        "radar": {
            "id": product.id,
            "label": product.label,
            "kind": product.kind.value,
            "cadenceMinutes": product.cadence_minutes,
        },
        "generatedAt": isoformat_utc(generated_at),
        "window": {
            "hours": history_hours,
            "start": isoformat_utc(window_start) if window_start is not None else None,
            "end": isoformat_utc(window_end) if window_end is not None else None,
            "anchor": "latest-available-frame",
        },
        "latestFrameTime": isoformat_utc(window_end) if window_end is not None else None,
        "latestProductTime": (
            isoformat_utc(latest_product_time) if latest_product_time is not None else None
        ),
        "timeBasis": _time_basis(selected),
        "frames": public_frames,
        "gaps": _detect_gaps(selected, product.cadence_minutes),
        "statistics": {
            "archivedFrames": len(frames),
            "publishedFrames": len(selected),
            "discardedDuplicates": scan.discarded_duplicates,
            "invalidReports": len(scan.issues),
        },
    }


def select_history_frames(
    frames: tuple[ArchivedFrame, ...],
    history_hours: float,
) -> tuple[ArchivedFrame, ...]:
    if not frames:
        return ()
    window_start = frames[-1].timeline_time - timedelta(hours=history_hours)
    return tuple(frame for frame in frames if frame.timeline_time >= window_start)


def _public_frame(
    frame: ArchivedFrame,
    product: RadarProduct,
    *,
    image_resolver: Callable[[RadarProduct, ArchivedFrame], FrameImage | None] | None,
) -> dict[str, object]:
    raw_url = "/" + "/".join(quote(part) for part in frame.raw_relative_path.split("/"))
    image = image_resolver(product, frame) if image_resolver is not None else None
    return {
        "id": f"{product.id}_{frame.source_hash[:16]}",
        "time": isoformat_utc(frame.timeline_time),
        "timeSource": frame.time_source,
        "productTime": (
            isoformat_utc(frame.product_time) if frame.product_time is not None else None
        ),
        "retrievedAt": isoformat_utc(frame.retrieved_at),
        "lastRetrievedAt": isoformat_utc(frame.last_retrieved_at),
        "sourceHash": f"sha256:{frame.source_hash}",
        "rawUrl": raw_url,
        "imageUrl": image.url if image is not None else None,
        "imageCoordinates": (
            [list(coordinate) for coordinate in image.coordinates] if image is not None else None
        ),
        "status": "available",
    }


def _time_basis(frames: tuple[ArchivedFrame, ...]) -> str | None:
    sources = {frame.time_source for frame in frames}
    if not sources:
        return None
    if len(sources) == 1:
        return next(iter(sources))
    return "mixed"


def _detect_gaps(
    frames: tuple[ArchivedFrame, ...],
    cadence_minutes: int,
) -> list[dict[str, object]]:
    if len(frames) < 2:
        return []

    cadence = timedelta(minutes=cadence_minutes)
    cadence_seconds = cadence.total_seconds()
    gaps: list[dict[str, object]] = []
    for previous, current in zip(frames, frames[1:]):
        elapsed = (current.timeline_time - previous.timeline_time).total_seconds()
        if elapsed + _GAP_JITTER_TOLERANCE_SECONDS < cadence_seconds * 1.5:
            continue
        missing_count = max(1, round(elapsed / cadence_seconds) - 1)
        expected_times = [
            isoformat_utc(previous.timeline_time + cadence * offset)
            for offset in range(1, missing_count + 1)
        ]
        gaps.append(
            {
                "after": isoformat_utc(previous.timeline_time),
                "before": isoformat_utc(current.timeline_time),
                "expectedCadenceMinutes": cadence_minutes,
                "missingCount": missing_count,
                "expectedTimes": expected_times,
                "timeBasis": (
                    previous.time_source if previous.time_source == current.time_source else "mixed"
                ),
            }
        )
    return gaps


def _load_json_object(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, object], payload)
