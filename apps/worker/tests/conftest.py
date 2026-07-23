from collections.abc import Callable
from io import BytesIO

import pytest
from PIL import Image


@pytest.fixture
def make_synthetic_gif() -> Callable[[bytes], bytes]:
    def make(comment: bytes = b"sanitized synthetic radar fixture") -> bytes:
        image = Image.new("P", (3, 2))
        palette = [
            0,
            0,
            0,
            0,
            128,
            255,
            255,
            255,
            0,
        ] + [0] * (256 * 3 - 9)
        image.putpalette(palette)
        image.putdata([0, 1, 2, 2, 1, 0])
        buffer = BytesIO()
        image.save(buffer, format="GIF", comment=comment)
        return buffer.getvalue()

    return make
