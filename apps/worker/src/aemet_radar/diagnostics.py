"""Informes seguros y persistentes para descargas que no superan validación."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aemet_radar.errors import DownloadValidationError
from aemet_radar.history import isoformat_utc
from aemet_radar.products import RadarProduct
from aemet_radar.storage import atomic_write_json


class FailureRecorder:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()

    def record_download_validation(
        self,
        *,
        product: RadarProduct,
        checked_at: datetime,
        attempts: int,
        error: DownloadValidationError,
    ) -> Path:
        checked_at_utc = checked_at.astimezone(UTC)
        filename = (
            checked_at_utc.strftime("%Y%m%dT%H%M%S%fZ") + f"-{product.id}-download-validation.json"
        )
        path = self.data_dir / "reports" / "phase-2" / "failures" / filename
        atomic_write_json(
            path,
            {
                "schemaVersion": 1,
                "generatedAt": isoformat_utc(checked_at),
                "product": {
                    "id": product.id,
                    "label": product.label,
                    "kind": product.kind.value,
                    "endpoint": product.endpoint,
                },
                "attempts": attempts,
                "error": {
                    "code": error.code,
                    "message": str(error),
                    "details": error.safe_details(),
                },
            },
        )
        return path
