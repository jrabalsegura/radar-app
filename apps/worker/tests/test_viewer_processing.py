from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from aemet_radar.errors import DownloadValidationError, ViewerNoDataError
from aemet_radar.viewer_processing import (
    inspect_viewer_png,
    publish_viewer_overlay,
)


def test_accepts_echoes_and_a_truly_dry_ppi() -> None:
    wet = _png(echo=True)
    dry = _png(echo=False)

    wet_result = inspect_viewer_png(wet, "image/png")
    dry_result = inspect_viewer_png(dry, "image/png")

    assert wet_result.echo_pixels == 1
    assert dry_result.echo_pixels == 0
    assert wet_result.width == 1000
    assert dry_result.height == 1000


def test_rejects_product_unavailable_artwork_and_html() -> None:
    unavailable = _png(echo=False, unavailable=True)

    with pytest.raises(ViewerNoDataError):
        inspect_viewer_png(unavailable, "image/png")
    with pytest.raises(DownloadValidationError):
        inspect_viewer_png(b"<html>temporary error</html>", "text/html")


def test_publishes_only_reflectivity_as_an_rgba_overlay(tmp_path: Path) -> None:
    content = _png(echo=True)
    inspection = inspect_viewer_png(content, "image/png")
    source = tmp_path / "source.png"
    source.write_bytes(content)
    coordinates = ((-10.0, 45.0), (0.0, 45.0), (0.0, 35.0), (-10.0, 35.0))

    report = publish_viewer_overlay(
        source,
        output_dir=tmp_path / "output",
        expected_sha256=inspection.sha256,
        coordinates=coordinates,
    )

    with Image.open(tmp_path / "output" / "overlay.png") as overlay:
        overlay.load()
        background_pixel = overlay.getpixel((0, 0))
        assert isinstance(background_pixel, tuple)
        assert background_pixel[3] == 0
        assert overlay.getpixel((1, 1)) == (255, 0, 0, 255)
    report_output = report["output"]
    assert isinstance(report_output, dict)
    assert report_output["maplibreCoordinates"] == [
        [-10.0, 45.0],
        [0.0, 45.0],
        [0.0, 35.0],
        [-10.0, 35.0],
    ]


def _png(*, echo: bool, unavailable: bool = False) -> bytes:
    image = Image.new("RGBA", (1000, 1000), (239, 242, 249, 179))
    image.putpixel((999, 999), (0, 0, 0, 0))
    if echo:
        image.putpixel((1, 1), (255, 0, 0, 255))
    if unavailable:
        image.putpixel((2, 2), (1, 1, 1, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
