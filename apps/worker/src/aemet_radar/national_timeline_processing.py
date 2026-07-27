"""Publicación incremental de derivados para la composición nacional."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import cast

from aemet_radar.history import ArchivedFrame
from aemet_radar.manifests import FrameImage
from aemet_radar.national_processing import (
    DEFAULT_GEOREFERENCING_CONFIG,
    DEFAULT_MASK_CONFIG,
    DEFAULT_PALETTE_CONFIG,
    PROCESSOR_ID,
    load_national_config,
    publish_national_overlay,
)
from aemet_radar.products import ProductKind, RadarProduct
from aemet_radar.viewer_client import MapCoordinates


class NationalTimelineProcessor:
    """Genera máscara y overlay nacional sin reutilizar parámetros regionales."""

    def __init__(
        self,
        data_dir: Path,
        *,
        palette_path: Path = DEFAULT_PALETTE_CONFIG,
        mask_path: Path = DEFAULT_MASK_CONFIG,
        georeferencing_path: Path = DEFAULT_GEOREFERENCING_CONFIG,
    ) -> None:
        self.data_dir = data_dir.resolve()
        self.palette_path = palette_path.resolve()
        self.mask_path = mask_path.resolve()
        self.georeferencing_path = georeferencing_path.resolve()
        self.configuration = load_national_config(
            palette_path=self.palette_path,
            mask_path=self.mask_path,
            georeferencing_path=self.georeferencing_path,
        )

    def ensure_frames(
        self,
        product: RadarProduct,
        frames: Iterable[ArchivedFrame],
    ) -> int:
        if product.kind is not ProductKind.NATIONAL:
            return 0
        processed = 0
        for frame in frames:
            if (
                frame.raw_path.suffix.lower() != ".png"
                or frame.source_provider != "aemet-viewer-national"
            ):
                continue
            if self._is_current(frame):
                continue
            coordinates = self._viewer_coordinates(frame)
            if coordinates is None:
                continue
            publish_national_overlay(
                frame.raw_path,
                output_dir=self._frame_dir(product, frame),
                expected_sha256=frame.source_hash,
                coordinates=coordinates,
                palette_path=self.palette_path,
                mask_path=self.mask_path,
                georeferencing_path=self.georeferencing_path,
            )
            processed += 1
        return processed

    def frame_image(
        self,
        product: RadarProduct,
        frame: ArchivedFrame,
    ) -> FrameImage | None:
        if product.kind is not ProductKind.NATIONAL or not self._is_current(frame):
            return None
        report = _load_json(self._frame_dir(product, frame) / "national-processing.json")
        output = _mapping(report.get("output")) if report is not None else {}
        coordinates = _map_coordinates(output.get("maplibreCoordinates"))
        if coordinates is None:
            return None
        return FrameImage(
            url=f"/radar/{product.id}/frames/{frame.source_hash}/overlay.png",
            coordinates=coordinates,
        )

    def radar_metadata(self, product: RadarProduct) -> dict[str, object]:
        if product.kind is not ProductKind.NATIONAL:
            return {}
        payload = _load_json(self.georeferencing_path)
        if payload is None:
            return {}
        map_config = _mapping(payload.get("map"))
        expected = _map_coordinates(payload.get("expectedMaplibreCoordinates"))
        center = _coordinate(map_config.get("center"))
        zoom = map_config.get("zoom")
        if (
            expected is None
            or center is None
            or not isinstance(zoom, (int, float))
            or isinstance(zoom, bool)
        ):
            return {}
        coverage_ring = [*expected, expected[0]]
        return {
            "regionCode": payload.get("regionCode"),
            "coverageLabel": payload.get("coverageLabel"),
            "includesCanaryIslands": payload.get("includesCanaryIslands"),
            "coordinates": list(center),
            "mapZoom": float(zoom),
            "coverageRing": [list(coordinate) for coordinate in coverage_ring],
            "validation": {
                "status": "verified",
                "sampleVerified": True,
            },
        }

    def validate_sample(
        self,
        source_path: Path,
        *,
        output_dir: Path,
        coordinates: MapCoordinates | None = None,
    ) -> dict[str, object]:
        selected_coordinates = (
            coordinates if coordinates is not None else self.configuration.expected_coordinates
        )
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        return publish_national_overlay(
            source_path,
            output_dir=output_dir,
            expected_sha256=source_hash,
            coordinates=selected_coordinates,
            palette_path=self.palette_path,
            mask_path=self.mask_path,
            georeferencing_path=self.georeferencing_path,
        )

    def _is_current(self, frame: ArchivedFrame) -> bool:
        frame_dir = self._frame_dir_for_id(frame.product_id, frame.source_hash)
        report = _load_json(frame_dir / "national-processing.json")
        if report is None:
            return False
        source = _mapping(report.get("source"))
        configuration = _mapping(report.get("configuration"))
        output = _mapping(report.get("output"))
        expected = self.configuration
        return (
            report.get("processor") == PROCESSOR_ID
            and source.get("sha256") == f"sha256:{frame.source_hash}"
            and configuration.get("paletteSha256") == f"sha256:{expected.palette_sha256}"
            and configuration.get("maskSha256") == f"sha256:{expected.mask_sha256}"
            and configuration.get("georeferencingSha256")
            == f"sha256:{expected.georeferencing_sha256}"
            and _map_coordinates(output.get("maplibreCoordinates")) is not None
            and (frame_dir / "mask.png").is_file()
            and (frame_dir / "overlay.png").is_file()
        )

    def _viewer_coordinates(
        self,
        frame: ArchivedFrame,
    ) -> MapCoordinates | None:
        report = _load_json(frame.report_path)
        viewer = _mapping(report.get("viewer")) if report is not None else {}
        return _map_coordinates(viewer.get("maplibreCoordinates"))

    def _frame_dir(
        self,
        product: RadarProduct,
        frame: ArchivedFrame,
    ) -> Path:
        return self._frame_dir_for_id(product.id, frame.source_hash)

    def _frame_dir_for_id(self, product_id: str, source_hash: str) -> Path:
        return self.data_dir / "radar" / product_id / "frames" / source_hash


def _load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _coordinate(value: object) -> tuple[float, float] | None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(
            isinstance(component, (int, float)) and not isinstance(component, bool)
            for component in value
        )
    ):
        return None
    return (float(value[0]), float(value[1]))


def _map_coordinates(value: object) -> MapCoordinates | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    result: list[tuple[float, float]] = []
    for coordinate in value:
        parsed = _coordinate(coordinate)
        if parsed is None:
            return None
        result.append(parsed)
    return cast(MapCoordinates, tuple(result))
