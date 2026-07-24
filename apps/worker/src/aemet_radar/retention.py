"""Retención coordinada de originales e informes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from aemet_radar.history import ArchivedFrame, scan_product_history
from aemet_radar.products import RadarProduct


@dataclass(frozen=True, slots=True)
class RetentionResult:
    product_id: str
    removed_frames: int
    retained_frames: int


class RetentionManager:
    def __init__(self, data_dir: Path, *, retention_hours: float = 24.0) -> None:
        if retention_hours <= 0:
            raise ValueError("retention_hours debe ser mayor que cero.")
        self.data_dir = data_dir.resolve()
        self.retention_hours = retention_hours

    def prune_product(
        self,
        product: RadarProduct,
        *,
        reference_time: datetime,
    ) -> RetentionResult:
        scan = scan_product_history(self.data_dir, product)
        if not scan.frames:
            return RetentionResult(product.id, removed_frames=0, retained_frames=0)

        cutoff = reference_time - timedelta(hours=self.retention_hours)
        latest = max(scan.frames, key=lambda frame: frame.timeline_time)
        removable = [
            frame
            for frame in scan.frames
            if frame.source_hash != latest.source_hash and frame.last_retrieved_at < cutoff
        ]
        for frame in removable:
            _remove_pair(frame)

        return RetentionResult(
            product.id,
            removed_frames=len(removable),
            retained_frames=len(scan.frames) - len(removable),
        )


def _remove_pair(frame: ArchivedFrame) -> None:
    """Elimina el par conocido; nunca busca fuera de las rutas ya validadas."""

    frame.report_path.unlink(missing_ok=True)
    frame.raw_path.unlink(missing_ok=True)
