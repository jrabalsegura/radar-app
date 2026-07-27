from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from aemet_radar.errors import AemetResponseError
from aemet_radar.national_client import AemetNationalClient


def test_parses_national_timeline_and_reorders_official_bounds() -> None:
    start = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    timeline = [_local_time(start + timedelta(minutes=10 * index)) for index in range(3)]
    elements = [_frame(start + timedelta(minutes=10 * index)) for index in (2, 0, 1)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/radar/timeline/compo/PB"):
            return httpx.Response(
                200,
                json=[
                    {
                        "Producto": "Composicion radar",
                        "Region": "Penbal",
                        "lineaTiempo": timeline,
                        "Elementos": elements,
                    }
                ],
                request=request,
            )
        if "/bounds-radar/compo/" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    [12.14, 27.22],
                    [12.14, 51.3],
                    [-16.08, 51.3],
                    [-16.08, 27.22],
                ],
                request=request,
            )
        raise AssertionError(request.url)

    http_client = httpx.Client(
        base_url="https://www.aemet.es/es/api-eltiempo",
        transport=httpx.MockTransport(handler),
    )
    with AemetNationalClient(http_client=http_client) as client:
        parsed = client.fetch_timeline()
        bounds = client.fetch_bounds(parsed.frames[-1])

    assert [frame.observed_at for frame in parsed.frames] == [
        start,
        start + timedelta(minutes=10),
        start + timedelta(minutes=20),
    ]
    assert parsed.frames[-1].file_name == "radw202607270820_3857.png"
    assert bounds == (
        (-16.08, 51.3),
        (12.14, 51.3),
        (12.14, 27.22),
        (-16.08, 27.22),
    )


def test_selects_exactly_the_visible_230_minutes() -> None:
    start = datetime(2026, 7, 27, 4, 0, tzinfo=UTC)
    times = [start + timedelta(minutes=10 * index) for index in range(30)]
    payload = [
        {
            "Producto": "Composicion radar",
            "Region": "Penbal",
            "lineaTiempo": [_local_time(value) for value in times],
            "Elementos": [_frame(value) for value in reversed(times)],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.Client(
        base_url="https://www.aemet.es/es/api-eltiempo",
        transport=httpx.MockTransport(handler),
    )
    with AemetNationalClient(http_client=http_client) as client:
        visible = client.fetch_timeline().visible_frames()

    assert len(visible) == 24
    assert visible[0].observed_at == times[-1] - timedelta(minutes=230)
    assert visible[-1].observed_at == times[-1]


def test_rejects_national_date_that_disagrees_with_filename() -> None:
    observed_at = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
    payload = [
        {
            "Producto": "Composicion radar",
            "Region": "Penbal",
            "lineaTiempo": [_local_time(observed_at)],
            "Elementos": [
                {
                    **_frame(observed_at),
                    "Fecha": "2026-07-27T10:10:00+02:00",
                }
            ],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.Client(
        base_url="https://www.aemet.es/es/api-eltiempo",
        transport=httpx.MockTransport(handler),
    )
    with AemetNationalClient(http_client=http_client) as client:
        with pytest.raises(AemetResponseError, match="no coincide"):
            client.fetch_timeline()


def _frame(observed_at: datetime) -> dict[str, str]:
    return {
        "producto": "Composicion radar",
        "Fecha": _local_time(observed_at),
        "Nombre fichero": f"radw{observed_at.strftime('%Y%m%d%H%M')}_3857.png",
    }


def _local_time(observed_at: datetime) -> str:
    return observed_at.astimezone(timezone(timedelta(hours=2))).isoformat()
