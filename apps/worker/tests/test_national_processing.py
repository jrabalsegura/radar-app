from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from aemet_radar.errors import ViewerNoDataError
from aemet_radar.national_processing import (
    inspect_national_png,
    publish_national_overlay,
)

COORDINATES = (
    (-16.08, 51.3),
    (12.14, 51.3),
    (12.14, 27.22),
    (-16.08, 27.22),
)


def test_builds_dynamic_mask_and_preserves_exact_reflectivity(
    tmp_path: Path,
) -> None:
    content = _national_png()
    inspection = inspect_national_png(content, "image/png")
    source = tmp_path / "source.png"
    source.write_bytes(content)

    report = publish_national_overlay(
        source,
        output_dir=tmp_path / "output",
        expected_sha256=inspection.sha256,
        coordinates=COORDINATES,
    )

    assert inspection.bit_depth == 4
    assert inspection.reflectivity_pixels == 2
    assert inspection.observed_reflectivity_rgb == (
        (0, 0, 252),
        (255, 255, 0),
    )
    assert report["processor"] == "national-v1"
    with Image.open(tmp_path / "output" / "mask.png") as mask:
        assert mask.mode == "L"
        assert mask.getpixel((10, 10)) == 255
        assert mask.getpixel((11, 10)) == 255
        assert mask.getpixel((12, 10)) == 0
    with Image.open(tmp_path / "output" / "overlay.png") as overlay:
        assert overlay.mode == "RGBA"
        assert overlay.getpixel((10, 10)) == (0, 0, 252, 255)
        assert overlay.getpixel((11, 10)) == (255, 255, 0, 255)
        transparent_pixel = overlay.getpixel((12, 10))
        assert isinstance(transparent_pixel, tuple)
        assert transparent_pixel[3] == 0


def test_accepts_a_dry_national_frame_without_inventing_echoes() -> None:
    inspection = inspect_national_png(_national_png(dry=True), "image/png")

    assert inspection.reflectivity_pixels == 0
    assert inspection.observed_reflectivity_rgb == ()


def test_rejects_the_observed_eight_bit_no_data_placeholder() -> None:
    with pytest.raises(ViewerNoDataError, match="profundidad"):
        inspect_national_png(_national_png(bit_depth=8), "image/png")


def _national_png(
    *,
    dry: bool = False,
    bit_depth: int = 4,
) -> bytes:
    image = Image.new("P", (962, 1079), 0)
    palette = [
        255,
        255,
        255,
        239,
        242,
        249,
        0,
        0,
        252,
        255,
        255,
        0,
        0,
        0,
        0,
    ] + [0] * (256 * 3 - 15)
    image.putpalette(palette)
    image.putpixel((12, 10), 1)
    image.putpixel((13, 10), 4)
    if not dry:
        image.putpixel((10, 10), 2)
        image.putpixel((11, 10), 3)
    buffer = BytesIO()
    transparency = bytes([0, 178, 178, 178, 178])
    image.save(
        buffer,
        format="PNG",
        bits=bit_depth,
        transparency=transparency,
    )
    return buffer.getvalue()
