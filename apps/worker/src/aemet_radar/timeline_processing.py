"""Publicación incremental de derivados temporales para Murcia."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from aemet_radar.georeferencing import georeference_overlay
from aemet_radar.history import ArchivedFrame
from aemet_radar.products import MURCIA, RadarProduct
from aemet_radar.reflectivity import process_reflectivity_sample


class MurciaTimelineProcessor:
    """Genera una única imagen pública y cacheable por original de Murcia."""

    def __init__(
        self,
        data_dir: Path,
        *,
        reflectivity_config_path: Path,
        static_mask_path: Path,
        georeferencing_config_path: Path,
    ) -> None:
        self.data_dir = data_dir.resolve()
        self.reflectivity_config_path = reflectivity_config_path.resolve()
        self.static_mask_path = static_mask_path.resolve()
        self.georeferencing_config_path = georeferencing_config_path.resolve()

    def ensure_frames(
        self,
        product: RadarProduct,
        frames: Iterable[ArchivedFrame],
    ) -> int:
        """Procesa los fotogramas que aún no tengan un derivado vigente."""

        if product.id != MURCIA.id:
            return 0
        processed = 0
        for frame in frames:
            if self._is_current(frame):
                continue
            reflectivity_dir = self._reflectivity_dir(frame)
            reflectivity = process_reflectivity_sample(
                frame.raw_path,
                config_path=self.reflectivity_config_path,
                static_mask_path=self.static_mask_path,
                output_dir=reflectivity_dir,
            )
            outputs = cast(dict[str, str], reflectivity.report["outputs"])
            georeference_overlay(
                reflectivity_dir / outputs["overlay"],
                config_path=self.georeferencing_config_path,
                output_dir=self._public_frame_dir(frame),
            )
            processed += 1
        return processed

    def image_url(self, product: RadarProduct, frame: ArchivedFrame) -> str | None:
        """Devuelve la URL estable solo cuando el derivado está completo."""

        if product.id != MURCIA.id or not self._is_current(frame):
            return None
        return f"/radar/{MURCIA.id}/frames/{frame.source_hash}/overlay-3857.png"

    def _is_current(self, frame: ArchivedFrame) -> bool:
        reflectivity_report = _load_json(self._reflectivity_dir(frame) / "report.json")
        georeferencing_report = _load_json(self._public_frame_dir(frame) / "georeferencing.json")
        if (
            reflectivity_report is None
            or georeferencing_report is None
            or not (self._public_frame_dir(frame) / "overlay-3857.png").is_file()
        ):
            return False

        source = _mapping(reflectivity_report.get("source"))
        reflectivity_config = _mapping(reflectivity_report.get("configuration"))
        georeferencing_config = _mapping(georeferencing_report.get("configuration"))
        return (
            source.get("sha256") == f"sha256:{frame.source_hash}"
            and reflectivity_config.get("paletteConfigSha256")
            == _prefixed_sha256(self.reflectivity_config_path)
            and reflectivity_config.get("staticMaskSha256")
            == _prefixed_sha256(self.static_mask_path)
            and georeferencing_config.get("sha256")
            == _prefixed_sha256(self.georeferencing_config_path)
        )

    def _reflectivity_dir(self, frame: ArchivedFrame) -> Path:
        return self.data_dir / "processed" / MURCIA.id / frame.source_hash / "reflectivity"

    def _public_frame_dir(self, frame: ArchivedFrame) -> Path:
        return self.data_dir / "radar" / MURCIA.id / "frames" / frame.source_hash


def _prefixed_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}
