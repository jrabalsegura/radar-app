from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

from aemet_radar.errors import GeoreferencingError
from aemet_radar.georeferencing import (
    georeference_overlay,
    load_georeferencing_config,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_CONFIG = REPOSITORY_ROOT / "config" / "georeferencing" / "regional-mu-v1.json"


def test_versioned_calibration_passes_with_subpixel_error() -> None:
    config = load_georeferencing_config(PRODUCTION_CONFIG)

    assert config.radar.code == "FTN"
    assert config.radar.longitude == pytest.approx(-1.18970006)
    assert config.radar.latitude == pytest.approx(38.26438295)
    assert config.radar.range_kilometres == 240
    assert config.source.metres_per_pixel == 1000
    assert config.source.center.x == 240
    assert config.source.center.y == 240
    assert len(config.control_points) == 8


def test_web_mercator_warp_is_deterministic_and_preserves_classes(
    tmp_path: Path,
) -> None:
    source_path = _write_overlay(tmp_path / "source.png")
    first = georeference_overlay(
        source_path,
        config_path=PRODUCTION_CONFIG,
        output_dir=tmp_path / "first",
    )
    second = georeference_overlay(
        source_path,
        config_path=PRODUCTION_CONFIG,
        output_dir=tmp_path / "second",
    )

    assert first.image_path.read_bytes() == second.image_path.read_bytes()
    assert first.report_path.read_bytes() == second.report_path.read_bytes()
    with Image.open(first.image_path) as output_image:
        output_image.load()
        assert output_image.mode == "RGBA"
        assert output_image.width > 480
        assert output_image.height > 480
        colours = {
            output_image.getpixel((x, y))
            for y in range(output_image.height)
            for x in range(output_image.width)
        }
    assert colours <= {
        (0, 0, 0, 0),
        (0, 0, 252, 255),
        (0, 148, 252, 255),
    }
    assert (0, 0, 252, 255) in colours
    assert (0, 148, 252, 255) in colours
    assert (255, 0, 0, 255) not in colours

    calibration = cast(dict[str, object], first.report["calibration"])
    assert calibration["status"] == "pass"
    assert calibration["controlPointCount"] == 8
    assert calibration["meanErrorKilometres"] == pytest.approx(0.368942)
    assert calibration["maximumErrorKilometres"] == pytest.approx(0.699806)

    output_report = cast(dict[str, object], first.report["output"])
    coordinates = cast(list[list[float]], output_report["maplibreCoordinates"])
    assert len(coordinates) == 4
    assert coordinates[0][0] < coordinates[1][0]
    assert coordinates[0][1] == coordinates[1][1]
    assert coordinates[2][1] == coordinates[3][1]
    assert coordinates[0][1] > coordinates[3][1]


def test_inaccurate_control_point_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(PRODUCTION_CONFIG.read_text(encoding="utf-8"))
    payload["calibration"]["controlPoints"][0]["observedPixel"]["x"] += 5
    bad_config = tmp_path / "bad.json"
    bad_config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GeoreferencingError) as captured:
        load_georeferencing_config(bad_config)

    details = captured.value.safe_details()
    assert cast(float, details["maximumErrorPixels"]) > 4
    assert details["acceptedErrorPixels"] == 1


def _write_overlay(path: Path) -> Path:
    image = Image.new("RGBA", (480, 480), (0, 0, 0, 0))
    image.putpixel((240, 240), (0, 0, 252, 255))
    image.putpixel((250, 240), (0, 148, 252, 255))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.save(path, format="PNG")
    return path
