"""Regenera los golden fixtures sintéticos y diminutos de la Fase 3."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "apps" / "worker" / "tests" / "fixtures" / "reflectivity"
)
SIZE = (6, 5)
CROP_SIZE = (6, 4)
SOURCE_INDEXES = (
    16,
    10,
    10,
    16,
    8,
    8,
    0,
    10,
    23,
    26,
    6,
    7,
    0,
    8,
    9,
    4,
    3,
    5,
    2,
    8,
    0,
    16,
    10,
    0,
    16,
    23,
    26,
    6,
    7,
    10,
)
STATIC_MASK = (
    255,
    0,
    255,
    255,
    0,
    255,
    255,
    0,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
    255,
)
REFLECTIVITY_RGB = {
    16: (0, 0, 252),
    23: (0, 148, 252),
    26: (0, 252, 252),
    6: (67, 131, 35),
    7: (0, 192, 0),
    8: (0, 255, 0),
    10: (255, 255, 0),
    9: (255, 187, 0),
    4: (255, 127, 0),
    3: (255, 0, 0),
    5: (200, 0, 90),
}


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    source = Image.new("P", SIZE)
    source.putpalette(_palette())
    source.putdata(SOURCE_INDEXES)
    source.save(FIXTURE_DIR / "source.gif", format="GIF", optimize=False)

    static_mask = Image.frombytes("L", CROP_SIZE, bytes(STATIC_MASK))
    static_mask.save(FIXTURE_DIR / "static-mask.png", format="PNG", compress_level=9)

    overlay_pixels: list[tuple[int, int, int, int]] = []
    alpha_pixels: list[int] = []
    for position, (palette_index, allowed) in enumerate(
        zip(SOURCE_INDEXES[:24], STATIC_MASK, strict=True)
    ):
        rgb = REFLECTIVITY_RGB.get(palette_index)
        x = position % CROP_SIZE[0]
        y = position // CROP_SIZE[0]
        inside_coverage = (x - 3) ** 2 + (y - 2) ** 2 <= 3**2
        opaque = rgb is not None and allowed == 255 and inside_coverage
        overlay_pixels.append((*rgb, 255) if opaque and rgb is not None else (0, 0, 0, 0))
        alpha_pixels.append(255 if opaque else 0)

    overlay = Image.new("RGBA", CROP_SIZE)
    overlay.putdata(overlay_pixels)
    overlay.save(FIXTURE_DIR / "expected-overlay.png", format="PNG", compress_level=9)
    alpha = Image.new("L", CROP_SIZE)
    alpha.putdata(alpha_pixels)
    alpha.save(FIXTURE_DIR / "expected-mask.png", format="PNG", compress_level=9)


def _palette() -> list[int]:
    values = [0] * (256 * 3)
    colors = {
        0: (0, 0, 0),
        2: (127, 127, 127),
        **REFLECTIVITY_RGB,
    }
    for index, rgb in colors.items():
        values[index * 3 : index * 3 + 3] = rgb
    return values


if __name__ == "__main__":
    main()
