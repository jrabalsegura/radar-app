"""Publicación incremental de derivados para la composición nacional."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from aemet_radar.common import (
    MapCoordinates,
    load_json_object,
    mapping,
    parse_coordinate,
    parse_map_coordinates,
    stored_viewer_coordinates,
)
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

NATIONAL_PUBLICATION_REVISION = "national-public-v2-coverage"


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
            coordinates = stored_viewer_coordinates(frame.report_path)
            if coordinates is None:
                continue
            publish_national_overlay(
                frame.raw_path,
                output_dir=self._versioned_frame_dir(frame),
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
        report = load_json_object(self._versioned_frame_dir(frame) / "national-processing.json")
        output = mapping(report.get("output")) if report is not None else {}
        coordinates = parse_map_coordinates(output.get("maplibreCoordinates"))
        if coordinates is None:
            return None
        return FrameImage(
            url="/"
            + (self._versioned_frame_dir(frame) / "overlay.png")
            .relative_to(self.data_dir)
            .as_posix(),
            no_coverage_url="/"
            + (self._versioned_frame_dir(frame) / "no-coverage.png")
            .relative_to(self.data_dir)
            .as_posix(),
            coordinates=coordinates,
        )

    def radar_metadata(self, product: RadarProduct) -> dict[str, object]:
        if product.kind is not ProductKind.NATIONAL:
            return {}
        payload = load_json_object(self.georeferencing_path)
        if payload is None:
            return {}
        map_config = mapping(payload.get("map"))
        expected = parse_map_coordinates(payload.get("expectedMaplibreCoordinates"))
        center = parse_coordinate(map_config.get("center"))
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
        frame_dir = self._versioned_frame_dir(frame)
        report = load_json_object(frame_dir / "national-processing.json")
        if report is None:
            return False
        source = mapping(report.get("source"))
        configuration = mapping(report.get("configuration"))
        output = mapping(report.get("output"))
        expected = self.configuration
        return (
            report.get("processor") == PROCESSOR_ID
            and source.get("sha256") == f"sha256:{frame.source_hash}"
            and configuration.get("paletteSha256") == f"sha256:{expected.palette_sha256}"
            and configuration.get("maskSha256") == f"sha256:{expected.mask_sha256}"
            and configuration.get("georeferencingSha256")
            == f"sha256:{expected.georeferencing_sha256}"
            and parse_map_coordinates(output.get("maplibreCoordinates")) is not None
            and (frame_dir / "mask.png").is_file()
            and (frame_dir / "overlay.png").is_file()
            and (frame_dir / "no-coverage.png").is_file()
        )

    def _versioned_frame_dir(self, frame: ArchivedFrame) -> Path:
        config = self.configuration
        version = hashlib.sha256(
            json.dumps(
                [
                    NATIONAL_PUBLICATION_REVISION,
                    PROCESSOR_ID,
                    config.palette_sha256,
                    config.mask_sha256,
                    config.georeferencing_sha256,
                    stored_viewer_coordinates(frame.report_path),
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return self.data_dir / "radar" / frame.product_id / "frames" / frame.source_hash / version
