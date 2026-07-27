from collections.abc import Callable

import httpx
import pytest

from aemet_radar.errors import AemetResponseError
from aemet_radar.viewer_client import (
    DEFAULT_VIEWER_BASE_URL,
    AemetViewerClient,
)


def test_parses_official_timeline_and_reorders_bounds_for_maplibre() -> None:
    timeline_payload = [
        {
            "Producto": "PPI.Z_005_240",
            "Elementos": [
                _element("CCD", "260727080000", "2026-07-27T10:00:00+02:00"),
                _element("CCD", "260727081000", "2026-07-27T10:10:00+02:00"),
                _element("SSE", "260727080000", "2026-07-27T10:00:00+02:00"),
            ],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/radar/timeline/PPI/PB"):
            return httpx.Response(200, json=timeline_payload, request=request)
        if "/bounds-radar/PPI/" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    [0.5, 35.0],
                    [0.5, 51.0],
                    [-17.5, 51.0],
                    [-17.5, 35.0],
                ],
                request=request,
            )
        raise AssertionError(f"Petición inesperada: {request.url}")

    client = _client(handler)
    try:
        timeline = client.fetch_timeline()
        ccd = timeline.frames_for("CCD")
        bounds = client.fetch_bounds(ccd[-1])
    finally:
        client.close()

    assert [frame.file_name for frame in ccd] == [
        "CCD260727080000.PPI.Z_005_240.png",
        "CCD260727081000.PPI.Z_005_240.png",
    ]
    assert ccd[0].observed_at.isoformat() == "2026-07-27T08:00:00+00:00"
    assert bounds == (
        (-17.5, 51.0),
        (0.5, 51.0),
        (0.5, 35.0),
        (-17.5, 35.0),
    )


def test_rejects_timeline_when_local_date_and_filename_disagree() -> None:
    payload = [
        {
            "Producto": "PPI.Z_005_240",
            "Elementos": [
                _element("CCD", "260727080000", "2026-07-27T10:10:00+02:00"),
            ],
        }
    ]
    client = _client(lambda request: httpx.Response(200, json=payload, request=request))

    try:
        with pytest.raises(AemetResponseError, match="no coincide"):
            client.fetch_timeline()
    finally:
        client.close()


def test_downloads_png_without_following_redirects() -> None:
    content = b"\x89PNG\r\n\x1a\nfixture"
    payload = [
        {
            "Producto": "PPI.Z_005_240",
            "Elementos": [
                _element("CCD", "260727080000", "2026-07-27T10:00:00+02:00"),
            ],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/radar/timeline/PPI/PB"):
            return httpx.Response(200, json=payload, request=request)
        return httpx.Response(
            200,
            content=content,
            headers={"Content-Type": "image/png"},
            request=request,
        )

    client = _client(handler)
    try:
        frame = client.fetch_timeline().frames[0]
        downloaded = client.fetch_image(frame)
    finally:
        client.close()

    assert downloaded.content == content
    assert downloaded.headers["content-type"] == "image/png"


def _element(site: str, timestamp: str, date: str) -> dict[str, str]:
    return {
        "Nombre radar": site,
        "Fecha": date,
        "Nombre fichero": f"{site}{timestamp}.PPI.Z_005_240.png",
        "producto": "PPI",
        "subproducto": "Z_005_240",
    }


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AemetViewerClient:
    return AemetViewerClient(
        http_client=httpx.Client(
            base_url=DEFAULT_VIEWER_BASE_URL,
            transport=httpx.MockTransport(handler),
        )
    )
