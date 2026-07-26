from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from aemet_radar.history import ArchivedFrame
from aemet_radar.products import MURCIA
from aemet_radar.timeline_processing import MurciaTimelineProcessor

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REFLECTIVITY_CONFIG = REPOSITORY_ROOT / "config" / "palettes" / "regional-mu-v1.json"
STATIC_MASK = REPOSITORY_ROOT / "config" / "masks" / "regional-mu-v1.png"
GEOREFERENCING_CONFIG = REPOSITORY_ROOT / "config" / "georeferencing" / "regional-mu-v1.json"


def test_murcia_timeline_processor_publishes_and_reuses_derived_frame(
    tmp_path: Path,
) -> None:
    raw_path = _write_production_shaped_gif(tmp_path / "source.gif")
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    observed_at = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    frame = ArchivedFrame(
        product_id=MURCIA.id,
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
    processor = MurciaTimelineProcessor(
        tmp_path,
        reflectivity_config_path=REFLECTIVITY_CONFIG,
        static_mask_path=STATIC_MASK,
        georeferencing_config_path=GEOREFERENCING_CONFIG,
    )

    assert processor.ensure_frames(MURCIA, (frame,)) == 1
    assert processor.ensure_frames(MURCIA, (frame,)) == 0
    assert processor.image_url(MURCIA, frame) == (
        f"/radar/regional-mu/frames/{digest}/overlay-3857.png"
    )

    output_dir = tmp_path / "radar" / MURCIA.id / "frames" / digest
    with Image.open(output_dir / "overlay-3857.png") as output:
        output.load()
        assert output.mode == "RGBA"
        assert output.size == (630, 618)
    report = json.loads((output_dir / "georeferencing.json").read_text())
    assert report["output"]["resampling"] == "nearest"


def _write_production_shaped_gif(path: Path) -> Path:
    config = json.loads(REFLECTIVITY_CONFIG.read_text(encoding="utf-8"))
    palette = [0] * (256 * 3)
    for item in config["classes"]:
        offset = item["paletteIndex"] * 3
        palette[offset : offset + 3] = item["rgb"]

    image = Image.new("P", (480, 530), 0)
    image.putpalette(palette)
    image.putpixel((250, 240), 16)
    image.save(path, format="GIF", optimize=False)
    return path
