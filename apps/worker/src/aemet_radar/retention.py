"""Retención coordinada con protección de publicaciones y margen para clientes abiertos."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from aemet_radar.history import scan_product_history
from aemet_radar.products import RadarProduct
from aemet_radar.storage import atomic_write_json

_HASH = re.compile(r"[0-9a-f]{64}")
DERIVED_GRACE_HOURS = 24


@dataclass(frozen=True, slots=True)
class RetentionResult:
    product_id: str
    removed_frames: int
    retained_frames: int
    removed_derivatives: int = 0
    reclaimed_bytes: int = 0


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
        candidates = scan.candidates or scan.frames
        # Si hay informes ilegibles no sabemos qué archivos siguen referenciados.
        if scan.issues:
            return RetentionResult(product.id, 0, len(candidates))
        protected_raw, protected_hashes, published_paths = self._published_references(product)
        cutoff = reference_time - timedelta(hours=self.retention_hours)
        latest = max(candidates, key=lambda frame: frame.timeline_time) if candidates else None
        removable = [
            frame
            for frame in candidates
            if frame != latest
            and frame.raw_path not in protected_raw
            and frame.last_retrieved_at < cutoff
        ]
        removable_reports = {frame.report_path for frame in removable}
        retained = [frame for frame in candidates if frame.report_path not in removable_reports]
        retained_raw = {frame.raw_path for frame in retained}
        live_hashes = protected_hashes | {frame.source_hash for frame in retained}
        for frame in removable:
            frame.report_path.unlink(missing_ok=True)
            if frame.raw_path not in retained_raw:
                frame.raw_path.unlink(missing_ok=True)

        removed_derivatives = reclaimed_bytes = 0
        ledger_path = self.data_dir / "state" / "retention" / f"{product.id}.json"
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
        if not isinstance(ledger, dict):
            raise ValueError("El registro de retención no es válido.")
        orphan_since: dict[str, object] = {}
        grace_cutoff = (reference_time - timedelta(hours=DERIVED_GRACE_HOURS)).timestamp()
        for parent in (
            self.data_dir / "processed" / product.id,
            self.data_dir / "radar" / product.id / "frames",
        ):
            if not parent.is_dir():
                continue
            for directory in parent.iterdir():
                if (
                    directory.is_symlink()
                    or not directory.is_dir()
                    or not _HASH.fullmatch(directory.name)
                ):
                    continue
                if directory.name in live_hashes:
                    # Versiones anteriores del mismo original se conservan mientras esté archivado.
                    continue
                if any(directory == path or directory in path.parents for path in published_paths):
                    continue
                key = directory.relative_to(self.data_dir).as_posix()
                since = ledger.get(key, reference_time.timestamp())
                if not isinstance(since, (int, float)):
                    since = reference_time.timestamp()
                orphan_since[key] = since
                if since >= grace_cutoff:
                    continue
                files = list(directory.rglob("*"))
                if any(path.is_symlink() for path in files):
                    continue
                if (
                    max([directory.stat().st_mtime, *(path.stat().st_mtime for path in files)])
                    >= grace_cutoff
                ):
                    continue
                size = sum(path.stat().st_size for path in files if path.is_file())
                shutil.rmtree(directory)
                removed_derivatives += 1
                reclaimed_bytes += size
                orphan_since.pop(key)
        atomic_write_json(ledger_path, orphan_since)
        return RetentionResult(
            product.id, len(removable), len(retained), removed_derivatives, reclaimed_bytes
        )

    def _published_references(self, product: RadarProduct) -> tuple[set[Path], set[str], set[Path]]:
        manifest_path = self.data_dir / "radar" / product.id / "manifest.json"
        if not manifest_path.exists():
            return set(), set(), set()
        # Un manifiesto ilegible detiene la limpieza, nunca equivale a ausencia de referencias.
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("frames"), list):
            raise ValueError("No se puede limpiar sin un manifiesto válido.")
        raw_paths: set[Path] = set()
        hashes: set[str] = set()
        paths: set[Path] = set()
        for frame in payload["frames"]:
            if not isinstance(frame, dict):
                raise ValueError("El manifiesto contiene un fotograma inválido.")
            digest = str(frame.get("sourceHash", "")).removeprefix("sha256:")
            if _HASH.fullmatch(digest):
                hashes.add(digest)
            for key in ("rawUrl", "imageUrl", "noCoverageUrl"):
                value = frame.get(key)
                if not isinstance(value, str) or not value.startswith("/"):
                    continue
                path = (self.data_dir / unquote(urlsplit(value).path).lstrip("/")).resolve()
                if not path.is_relative_to(self.data_dir):
                    raise ValueError("Una referencia pública sale del directorio de datos.")
                paths.add(path)
                if key == "rawUrl":
                    raw_paths.add(path)
        return raw_paths, hashes, paths
