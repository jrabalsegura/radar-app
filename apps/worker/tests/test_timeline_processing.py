from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from aemet_radar.history import ArchivedFrame
from aemet_radar.products import MURCIA
from aemet_radar.radar_catalog import load_radar_catalog
from aemet_radar.timeline_processing import RegionalTimelineProcessor

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REFLECTIVITY_CONFIG = REPOSITORY_ROOT / "config" / "palettes" / "regional-mu-v1.json"
SAFE_REFLECTIVITY_CONFIG = REPOSITORY_ROOT / "config" / "palettes" / "regional-safe-v1.json"
STATIC_MASK = REPOSITORY_ROOT / "config" / "masks" / "regional-mu-v1.png"
GEOREFERENCING_CONFIG = REPOSITORY_ROOT / "config" / "georeferencing" / "regional-mu-v1.json"
RADAR_CATALOG = REPOSITORY_ROOT / "config" / "radars.yaml"


def test_murcia_timeline_processor_publishes_and_reuses_derived_frame(
    tmp_path: Path,
) -> None:
    raw_path = _write_production_shaped_gif(tmp_path / "source.gif")
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    observed_at = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    frame = ArchivedFrame(
        product_id=MURCIA.id,
        source_id=digest,
        source_provider=None,
        source_hash=digest,
        product_time=observed_at,
        retrieved_at=observed_at,
        last_retrieved_at=observed_at,
        timeline_time=observed_at,
        time_source="productTime",
        raw_path=raw_path,
        raw_relative_path="raw/regional-mu/source.gif",
        report_path=tmp_path / "source.json",
    )
    processor = RegionalTimelineProcessor(
        tmp_path,
        catalog=load_radar_catalog(RADAR_CATALOG),
    )

    assert processor.ensure_frames(MURCIA, (frame,)) == 1
    assert processor.ensure_frames(MURCIA, (frame,)) == 0
    image = processor.frame_image(MURCIA, frame)
    assert image is not None
    assert image.url == (f"/radar/regional-mu/frames/{digest}/overlay-3857.png")
    assert len(image.coordinates) == 4

    output_dir = tmp_path / "radar" / MURCIA.id / "frames" / digest
    with Image.open(output_dir / "overlay-3857.png") as output:
        output.load()
        assert output.mode == "RGBA"
        assert output.size == (630, 618)
    report = json.loads((output_dir / "georeferencing.json").read_text())
    assert report["output"]["resampling"] == "nearest"


def test_viewer_timeline_processor_uses_official_png_bounds_without_masks(
    tmp_path: Path,
) -> None:
    raw_path = tmp_path / "source.png"
    source = Image.new("RGBA", (1000, 1000), (239, 242, 249, 179))
    source.putpixel((1, 1), (255, 0, 0, 255))
    source.putpixel((999, 999), (0, 0, 0, 0))
    source.save(raw_path)
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    observed_at = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    report_path = tmp_path / "source.json"
    coordinates = [[-7.0, 42.0], [4.0, 42.0], [4.0, 34.0], [-7.0, 34.0]]
    report_path.write_text(
        json.dumps({"viewer": {"maplibreCoordinates": coordinates}}),
        encoding="utf-8",
    )
    frame = ArchivedFrame(
        product_id=MURCIA.id,
        source_id="FTN260727080000.PPI.Z_005_240.png",
        source_provider="aemet-viewer",
        source_hash=digest,
        product_time=observed_at,
        retrieved_at=observed_at,
        last_retrieved_at=observed_at,
        timeline_time=observed_at,
        time_source="productTime",
        raw_path=raw_path,
        raw_relative_path="raw/regional-mu/source.png",
        report_path=report_path,
    )
    processor = RegionalTimelineProcessor(
        tmp_path,
        catalog=load_radar_catalog(RADAR_CATALOG),
    )

    assert processor.ensure_frames(MURCIA, (frame,)) == 1
    assert processor.ensure_frames(MURCIA, (frame,)) == 0
    image = processor.frame_image(MURCIA, frame)

    assert image is not None
    assert image.url == f"/radar/regional-mu/frames/{digest}/overlay.png"
    assert image.coordinates == tuple(tuple(value) for value in coordinates)
    with Image.open(tmp_path / "radar" / MURCIA.id / "frames" / digest / "overlay.png") as overlay:
        overlay.load()
        assert overlay.size == (1000, 1000)
        background_pixel = overlay.getpixel((0, 0))
        assert isinstance(background_pixel, tuple)
        assert background_pixel[3] == 0
        assert overlay.getpixel((1, 1)) == (255, 0, 0, 255)


def test_reviewed_dry_profile_validates_a_different_radar_geometry(
    tmp_path: Path,
) -> None:
    catalog = load_radar_catalog(RADAR_CATALOG)
    definition = catalog.definition_for("regional-ml")
    source = _write_production_shaped_gif(
        tmp_path / "malaga.gif",
        config_path=SAFE_REFLECTIVITY_CONFIG,
        include_yellow=True,
    )
    processor = RegionalTimelineProcessor(tmp_path, catalog=catalog)

    report = processor.validate_sample(
        definition.product,
        source,
        output_dir=tmp_path / "validation",
    )

    assert report["status"] == "pass"
    validation = report["validation"]
    assert isinstance(validation, dict)
    assert validation["validationMode"] == "official-geometry"
    reflectivity = json.loads(
        (tmp_path / "validation" / "reflectivity" / "report.json").read_text()
    )
    assert reflectivity["productId"] == "regional-ml"
    yellow = reflectivity["ambiguities"]["yellow"]
    assert yellow["policy"] == "static-mask"
    assert yellow["result"]["discardedByAmbiguousPolicy"] == 0
    assert yellow["result"]["keptPixels"] + yellow["result"]["discardedByStaticMask"] == 1
    assert (tmp_path / "validation" / "calibration" / "overlay-3857.png").is_file()


def test_calibrated_generic_profile_uses_its_catalog_mask_policy(tmp_path: Path) -> None:
    catalog = load_radar_catalog(RADAR_CATALOG)
    definition = catalog.definition_for("regional-ba")
    source = _write_production_shaped_gif(
        tmp_path / "barcelona.gif",
        config_path=SAFE_REFLECTIVITY_CONFIG,
        include_yellow=True,
    )
    processor = RegionalTimelineProcessor(tmp_path, catalog=catalog)

    processor.validate_sample(
        definition.product,
        source,
        output_dir=tmp_path / "validation",
    )

    reflectivity = json.loads(
        (tmp_path / "validation" / "reflectivity" / "report.json").read_text()
    )
    yellow = reflectivity["ambiguities"]["yellow"]
    assert yellow["policy"] == "static-mask"
    assert yellow["result"]["discardedByAmbiguousPolicy"] == 0
    assert yellow["result"]["keptPixels"] + yellow["result"]["discardedByStaticMask"] == 1


def _write_production_shaped_gif(
    path: Path,
    *,
    config_path: Path = REFLECTIVITY_CONFIG,
    include_yellow: bool = False,
) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    palette = [0] * (256 * 3)
    for item in config["classes"]:
        offset = item["paletteIndex"] * 3
        palette[offset : offset + 3] = item["rgb"]

    image = Image.new("P", (480, 530), 0)
    image.putpalette(palette)
    image.putpixel((250, 240), 16)
    if include_yellow:
        image.putpixel((200, 200), 10)
    image.save(path, format="GIF", optimize=False)
    return path
