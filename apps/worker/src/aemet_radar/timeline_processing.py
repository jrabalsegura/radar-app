"""Publicación incremental de derivados para radares regionales."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image

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
from aemet_radar.history import ArchivedFrame
from aemet_radar.manifests import FrameImage, MapCoordinates
from aemet_radar.products import RadarProduct
from aemet_radar.radar_catalog import RadarCatalog, RadarDefinition
from aemet_radar.reflectivity import (
    load_reflectivity_config,
    process_reflectivity_sample,
)
from aemet_radar.storage import atomic_write_bytes, atomic_write_json


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
            if self._is_current(definition, frame):
                continue
            reflectivity_dir = self._reflectivity_dir(product, frame)
            reflectivity = process_reflectivity_sample(
                frame.raw_path,
                config_path=definition.reflectivity_config_path,
                static_mask_path=definition.static_mask_path,
                output_dir=reflectivity_dir,
                product_id=product.id,
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
        if definition is None or not self._is_current(definition, frame):
            return None
        report = _load_json(self._public_frame_dir(product, frame) / "georeferencing.json")
        output = _mapping(report.get("output")) if report is not None else {}
        coordinates = _map_coordinates(output.get("maplibreCoordinates"))
        if coordinates is None:
            return None
        return FrameImage(
            url=f"/radar/{product.id}/frames/{frame.source_hash}/overlay-3857.png",
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
        reflectivity_report = _load_json(self._reflectivity_dir(product, frame) / "report.json")
        georeferencing_report = _load_json(
            self._public_frame_dir(product, frame) / "georeferencing.json"
        )
        if (
            reflectivity_report is None
            or georeferencing_report is None
            or not (self._public_frame_dir(product, frame) / "overlay-3857.png").is_file()
        ):
            return False

        source = _mapping(reflectivity_report.get("source"))
        reflectivity_config = _mapping(reflectivity_report.get("configuration"))
        georeferencing_config = _mapping(georeferencing_report.get("configuration"))
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
            and georeferencing_config.get("sha256") == self._georeferencing_sha256(definition)
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
        return self.data_dir / "radar" / product.id / "frames" / frame.source_hash


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


def _load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _map_coordinates(value: object) -> MapCoordinates | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    result: list[tuple[float, float]] = []
    for coordinate in value:
        if (
            not isinstance(coordinate, list)
            or len(coordinate) != 2
            or not all(
                isinstance(component, (int, float)) and not isinstance(component, bool)
                for component in coordinate
            )
        ):
            return None
        result.append((float(coordinate[0]), float(coordinate[1])))
    return cast(MapCoordinates, tuple(result))


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


# Nombre conservado para consumidores de la Fase 5.
MurciaTimelineProcessor = RegionalTimelineProcessor
