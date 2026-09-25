"""Publicación incremental de derivados nacionales y regionales."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image

from aemet_radar.common import (
    load_json_object,
    mapping,
    parse_map_coordinates,
    stored_viewer_coordinates,
)
from aemet_radar.georeferencing import (
    PROCESSOR_ID as GEOREFERENCING_PROCESSOR,
)
from aemet_radar.georeferencing import (
    GeoreferencingConfig,
    GeoreferencingResult,
    OutputRaster,
    Pixel,
    Radar,
    SourceRaster,
    coverage_ring,
    georeference_overlay,
    load_georeferencing_config,
)
from aemet_radar.history import ArchivedFrame, HistoryScan
from aemet_radar.manifests import FrameImage, select_history_frames
from aemet_radar.national_timeline_processing import NationalTimelineProcessor
from aemet_radar.products import ProductKind, RadarProduct
from aemet_radar.radar_catalog import RadarCatalog, RadarDefinition
from aemet_radar.reflectivity import (
    load_reflectivity_config,
    process_reflectivity_sample,
)
from aemet_radar.storage import atomic_write_bytes, atomic_write_json
from aemet_radar.temporal import HISTORY_HOURS
from aemet_radar.viewer_processing import PROCESSOR_ID as VIEWER_PROCESSOR
from aemet_radar.viewer_processing import publish_viewer_overlay

# Debe cambiar al modificar el algoritmo; forma parte de la URL pública inmutable.
REGIONAL_PROCESSING_REVISION = "regional-public-v2-ambiguous-mask"


def frames_for_processing(product: RadarProduct, scan: HistoryScan) -> tuple[ArchivedFrame, ...]:
    candidates = scan.candidates or scan.frames
    if product.kind is ProductKind.NATIONAL:
        candidates = tuple(
            frame
            for frame in candidates
            if frame.raw_path.suffix == ".png" and frame.source_provider == "aemet-viewer-national"
        )
    ordered = tuple(sorted(candidates, key=lambda frame: frame.timeline_time))
    return select_history_frames(ordered, HISTORY_HOURS)


class RegionalTimelineProcessor:
    """Genera una imagen pública inmutable por original y radar."""

    def __init__(self, data_dir: Path, *, catalog: RadarCatalog) -> None:
        self.data_dir = data_dir.resolve()
        self.catalog = catalog

    def ensure_frames(
        self,
        product: RadarProduct,
        frames: Iterable[ArchivedFrame],
    ) -> int:
        """Procesa los fotogramas regionales que aún no estén vigentes."""

        definition = self._definition(product)
        if definition is None:
            return 0
        processed = 0
        for frame in frames:
            if frame.raw_path.suffix.lower() == ".png":
                if self._viewer_is_current(frame):
                    continue
                coordinates = stored_viewer_coordinates(frame.report_path)
                if coordinates is None:
                    continue
                publish_viewer_overlay(
                    frame.raw_path,
                    output_dir=self._public_frame_dir(product, frame),
                    expected_sha256=frame.source_hash,
                    coordinates=coordinates,
                )
                processed += 1
                continue
            if self._is_current(definition, frame):
                continue
            reflectivity_dir = self._reflectivity_dir(product, frame)
            reflectivity = process_reflectivity_sample(
                frame.raw_path,
                config_path=definition.reflectivity_config_path,
                static_mask_path=definition.static_mask_path,
                output_dir=reflectivity_dir,
                product_id=product.id,
                ambiguous_class_policy=definition.ambiguous_class_policy,
            )
            outputs = cast(dict[str, str], reflectivity.report["outputs"])
            self._georeference(
                definition,
                reflectivity_dir / outputs["overlay"],
                self._public_frame_dir(product, frame),
            )
            processed += 1
        return processed

    def frame_image(
        self,
        product: RadarProduct,
        frame: ArchivedFrame,
    ) -> FrameImage | None:
        """Resuelve URL y esquinas solo para un derivado completo y vigente."""

        definition = self._definition(product)
        if definition is None:
            return None
        if frame.raw_path.suffix.lower() == ".png":
            if not self._viewer_is_current(frame):
                return None
            report = load_json_object(
                self._public_frame_dir(product, frame) / "viewer-processing.json"
            )
            output = mapping(report.get("output")) if report is not None else {}
            coordinates = parse_map_coordinates(output.get("maplibreCoordinates"))
            if coordinates is None:
                return None
            return FrameImage(
                url="/"
                + (self._public_frame_dir(product, frame) / "overlay.png")
                .relative_to(self.data_dir)
                .as_posix(),
                coordinates=coordinates,
            )
        if not self._is_current(definition, frame):
            return None
        report = load_json_object(self._public_frame_dir(product, frame) / "georeferencing.json")
        output = mapping(report.get("output")) if report is not None else {}
        coordinates = parse_map_coordinates(output.get("maplibreCoordinates"))
        if coordinates is None:
            return None
        return FrameImage(
            url="/"
            + (self._public_frame_dir(product, frame) / "overlay-3857.png")
            .relative_to(self.data_dir)
            .as_posix(),
            coordinates=coordinates,
        )

    def radar_metadata(self, product: RadarProduct) -> dict[str, object]:
        """Publica emplazamiento, cobertura y estado de validación."""

        definition = self._definition(product)
        if definition is None:
            return {}
        radar = Radar(
            code=definition.site_code,
            name=definition.site_name,
            longitude=definition.longitude,
            latitude=definition.latitude,
            range_kilometres=definition.range_kilometres,
        )
        return {
            "apiCode": definition.product.aemet_code,
            "siteCode": definition.site_code,
            "siteName": definition.site_name,
            "coordinates": [definition.longitude, definition.latitude],
            "mapCenter": [
                definition.map_center_longitude,
                definition.map_center_latitude,
            ],
            "rangeKilometres": definition.range_kilometres,
            "mapZoom": definition.map_zoom,
            "coverageRing": coverage_ring(radar),
            "validation": {
                "status": definition.sample_validation,
                "sampleVerified": definition.sample_verified,
            },
        }

    def validate_sample(
        self,
        product: RadarProduct,
        source_path: Path,
        *,
        output_dir: Path,
    ) -> dict[str, object]:
        """Valida plantilla y proyección y genera límites revisables."""

        definition = self.catalog.definition_for(product.id)
        reflectivity_dir = output_dir / "reflectivity"
        reflectivity = process_reflectivity_sample(
            source_path,
            config_path=definition.reflectivity_config_path,
            static_mask_path=definition.static_mask_path,
            output_dir=reflectivity_dir,
            product_id=product.id,
            ambiguous_class_policy=definition.ambiguous_class_policy,
        )
        outputs = cast(dict[str, str], reflectivity.report["outputs"])
        georeferenced = self._georeference(
            definition,
            reflectivity_dir / outputs["overlay"],
            output_dir / "georeferenced",
        )
        boundary_path = output_dir / "calibration-boundaries.png"
        _write_boundary_layer(
            source_path,
            definition=definition,
            output_path=boundary_path,
        )
        boundary_georeferenced = self._georeference(
            definition,
            boundary_path,
            output_dir / "calibration",
        )
        report: dict[str, object] = {
            "schemaVersion": 1,
            "productId": product.id,
            "status": "pass",
            "sampleValidation": definition.sample_validation,
            "source": reflectivity.report["source"],
            "reflectivityReport": reflectivity.report_path.relative_to(output_dir).as_posix(),
            "georeferencingReport": georeferenced.report_path.relative_to(output_dir).as_posix(),
            "overlay": georeferenced.image_path.relative_to(output_dir).as_posix(),
            "calibrationPreview": (
                boundary_georeferenced.image_path.relative_to(output_dir).as_posix()
            ),
            "validation": georeferenced.report["calibration"],
            "configurationSha256": self._georeferencing_sha256(definition),
        }
        atomic_write_json(output_dir / "validation.json", report)
        return report

    def _definition(self, product: RadarProduct) -> RadarDefinition | None:
        try:
            return self.catalog.definition_for(product.id)
        except KeyError:
            return None

    def _georeference(
        self,
        definition: RadarDefinition,
        source_path: Path,
        output_dir: Path,
    ) -> GeoreferencingResult:
        georeferencing_path = definition.georeferencing_config_path
        if georeferencing_path is not None:
            return georeference_overlay(
                source_path,
                config_path=georeferencing_path,
                output_dir=output_dir,
            )
        return georeference_overlay(
            source_path,
            configuration=_catalog_georeferencing(definition),
            configuration_sha256=self._georeferencing_sha256(definition),
            output_dir=output_dir,
        )

    def _is_current(
        self,
        definition: RadarDefinition,
        frame: ArchivedFrame,
    ) -> bool:
        product = definition.product
        reflectivity_report = load_json_object(
            self._reflectivity_dir(product, frame) / "report.json"
        )
        georeferencing_report = load_json_object(
            self._public_frame_dir(product, frame) / "georeferencing.json"
        )
        if (
            reflectivity_report is None
            or georeferencing_report is None
            or not (self._public_frame_dir(product, frame) / "overlay-3857.png").is_file()
        ):
            return False

        source = mapping(reflectivity_report.get("source"))
        reflectivity_config = mapping(reflectivity_report.get("configuration"))
        georeferencing_config = mapping(georeferencing_report.get("configuration"))
        expected_mask_sha256 = (
            _prefixed_sha256(definition.static_mask_path)
            if definition.static_mask_path is not None
            else None
        )
        return (
            reflectivity_report.get("productId") == product.id
            and source.get("sha256") == f"sha256:{frame.source_hash}"
            and reflectivity_config.get("paletteConfigSha256")
            == _prefixed_sha256(definition.reflectivity_config_path)
            and reflectivity_config.get("staticMaskSha256") == expected_mask_sha256
            and reflectivity_config.get("ambiguousClassPolicy") == definition.ambiguous_class_policy
            and georeferencing_config.get("sha256") == self._georeferencing_sha256(definition)
        )

    def _viewer_is_current(self, frame: ArchivedFrame) -> bool:
        frame_dir = self._public_frame_dir(
            self.catalog.definition_for(frame.product_id).product, frame
        )
        report = load_json_object(frame_dir / "viewer-processing.json")
        if report is None:
            return False
        source = mapping(report.get("source"))
        output = mapping(report.get("output"))
        return (
            report.get("processor") == VIEWER_PROCESSOR
            and source.get("sha256") == f"sha256:{frame.source_hash}"
            and parse_map_coordinates(output.get("maplibreCoordinates")) is not None
            and (frame_dir / "overlay.png").is_file()
        )

    def _georeferencing_sha256(self, definition: RadarDefinition) -> str:
        if definition.georeferencing_config_path is not None:
            return _prefixed_sha256(definition.georeferencing_config_path)
        return f"sha256:{definition.configuration_sha256}"

    def _reflectivity_dir(
        self,
        product: RadarProduct,
        frame: ArchivedFrame,
    ) -> Path:
        return self.data_dir / "processed" / product.id / frame.source_hash / "reflectivity"

    def _public_frame_dir(
        self,
        product: RadarProduct,
        frame: ArchivedFrame,
    ) -> Path:
        definition = self.catalog.definition_for(product.id)
        if frame.raw_path.suffix.lower() == ".png":
            configuration = [VIEWER_PROCESSOR, stored_viewer_coordinates(frame.report_path)]
        else:
            configuration = [
                REGIONAL_PROCESSING_REVISION,
                _prefixed_sha256(definition.reflectivity_config_path),
                _prefixed_sha256(definition.static_mask_path)
                if definition.static_mask_path
                else None,
                definition.ambiguous_class_policy,
                self._georeferencing_sha256(definition),
            ]
        version = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
        return self.data_dir / "radar" / product.id / "frames" / frame.source_hash / version


def _catalog_georeferencing(
    definition: RadarDefinition,
) -> GeoreferencingConfig:
    if definition.georeferencing_config_path is not None:
        return load_georeferencing_config(definition.georeferencing_config_path)
    source = definition.source_raster
    output = definition.output_raster
    projection = (
        f"+proj=aeqd +lat_0={definition.latitude} "
        f"+lon_0={definition.longitude} +datum=WGS84 +units=m +no_defs"
    )
    return GeoreferencingConfig(
        schema_version=1,
        product_id=definition.product.id,
        processor=GEOREFERENCING_PROCESSOR,
        radar=Radar(
            code=definition.site_code,
            name=definition.site_name,
            longitude=definition.longitude,
            latitude=definition.latitude,
            range_kilometres=definition.range_kilometres,
        ),
        source=SourceRaster(
            width=source.width,
            height=source.height,
            center=Pixel(x=source.center_x, y=source.center_y),
            metres_per_pixel=source.metres_per_pixel,
            projection=projection,
        ),
        output=OutputRaster(
            crs=output.crs,
            pixel_size_metres=output.pixel_size_metres,
            resampling=output.resampling,
        ),
        control_points=(),
        maximum_error_pixels=1.0,
        validation_mode="official-geometry",
        validation_method=(
            "Centro oficial del visor AEMET y contrato regional de 1 km por "
            "píxel, 240 km de alcance y proyección azimutal equidistante."
        ),
        validation_reference=("https://www.aemet.es/es/eltiempo/observacion/radar.html"),
    )


def _prefixed_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_boundary_layer(
    source_path: Path,
    *,
    definition: RadarDefinition,
    output_path: Path,
) -> None:
    config = load_reflectivity_config(
        definition.reflectivity_config_path,
        product_id=definition.product.id,
    )
    with Image.open(source_path) as source:
        source.seek(0)
        source.load()
        crop = source.crop(config.crop.pillow_box).convert("RGB")
    source_pixels = crop.tobytes()
    output = bytearray(config.crop.width * config.crop.height * 4)
    for position in range(config.crop.width * config.crop.height):
        source_offset = position * 3
        if source_pixels[source_offset : source_offset + 3] == bytes((255, 255, 0)):
            output_offset = position * 4
            output[output_offset : output_offset + 4] = bytes((255, 106, 61, 220))
    image = Image.frombytes(
        "RGBA",
        (config.crop.width, config.crop.height),
        bytes(output),
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG", compress_level=9)
    atomic_write_bytes(output_path, buffer.getvalue())


class RadarTimelineProcessor(RegionalTimelineProcessor):
    """Despacha procesadores regional y nacional manteniéndolos independientes."""

    def __init__(self, data_dir: Path, *, catalog: RadarCatalog) -> None:
        super().__init__(data_dir, catalog=catalog)
        self.national = NationalTimelineProcessor(data_dir)

    def ensure_frames(
        self,
        product: RadarProduct,
        frames: Iterable[ArchivedFrame],
    ) -> int:
        if product.kind is ProductKind.NATIONAL:
            return self.national.ensure_frames(product, frames)
        return super().ensure_frames(product, frames)

    def frame_image(
        self,
        product: RadarProduct,
        frame: ArchivedFrame,
    ) -> FrameImage | None:
        if product.kind is ProductKind.NATIONAL:
            return self.national.frame_image(product, frame)
        return super().frame_image(product, frame)

    def radar_metadata(self, product: RadarProduct) -> dict[str, object]:
        if product.kind is ProductKind.NATIONAL:
            return self.national.radar_metadata(product)
        return super().radar_metadata(product)
