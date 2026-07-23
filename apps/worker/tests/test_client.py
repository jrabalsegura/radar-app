import json
from collections.abc import Callable

import httpx
import pytest

from aemet_radar.client import DEFAULT_BASE_URL, AemetClient
from aemet_radar.errors import (
    AemetApiStatusError,
    AemetHttpError,
    AemetResponseError,
    AemetTransportError,
)
from aemet_radar.products import MURCIA

FAKE_SECRET = "fixture-secret-that-must-never-leak"
DATA_URL = "https://opendata.aemet.es/opendata/sh/sanitized-data"
METADATA_URL = "https://opendata.aemet.es/opendata/sh/sanitized-metadata"


def test_fetches_gateway_data_and_metadata_without_forwarding_api_key(
    make_synthetic_gif: Callable[[bytes], bytes],
) -> None:
    gif = make_synthetic_gif(b"sanitized synthetic radar fixture")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/api/red/radar/regional/mu"):
            assert request.headers["api_key"] == FAKE_SECRET
            return httpx.Response(
                200,
                json={
                    "descripcion": "exito",
                    "estado": 200,
                    "datos": DATA_URL,
                    "metadatos": METADATA_URL,
                },
                headers={"Date": "Thu, 23 Jul 2026 12:35:00 GMT"},
            )
        assert "api_key" not in request.headers
        if request.url == httpx.URL(DATA_URL):
            return httpx.Response(
                200,
                content=gif,
                headers={
                    "Content-Type": "image/gif",
                    "Last-Modified": "Thu, 23 Jul 2026 12:30:00 GMT",
                },
            )
        if request.url == httpx.URL(METADATA_URL):
            encoded_metadata = json.dumps(
                {
                    "formato": "image/gif",
                    "periodicidad": "cada 10 minutos",
                    "descripcion": "Teledetección de España",
                },
                ensure_ascii=False,
            ).encode("iso-8859-15")
            return httpx.Response(
                200,
                content=encoded_metadata,
                headers={"Content-Type": "application/json;charset=ISO-8859-15"},
            )
        raise AssertionError(f"Petición inesperada: {request.url.path}")

    with _mocked_client(handler) as client:
        result = client.fetch_product(MURCIA)

    assert result.content == gif
    assert result.resource_name == "sanitized-data"
    assert result.data_headers["content-type"] == "image/gif"
    assert result.metadata.status == "ok"
    assert len(requests) == 3


def test_distinguishes_api_status_from_http_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"descripcion": "sin datos", "estado": 404},
            request=request,
        )

    with _mocked_client(handler) as client, pytest.raises(AemetApiStatusError) as captured:
        client.fetch_product(MURCIA)

    assert captured.value.status_code == 404
    assert "HTTP" not in str(captured.value)


def test_probe_checks_gateway_without_downloading_data() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "descripcion": "exito",
                "estado": 200,
                "datos": DATA_URL,
                "metadatos": METADATA_URL,
            },
            request=request,
        )

    with _mocked_client(handler) as client:
        result = client.probe_product(MURCIA)

    assert result.status == "available"
    assert result.api_status == 200
    assert result.has_data_url is True
    assert len(requests) == 1


def test_probe_records_unavailable_api_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"descripcion": "sin datos", "estado": 404},
            request=request,
        )

    with _mocked_client(handler) as client:
        result = client.probe_product(MURCIA)

    assert result.status == "unavailable"
    assert result.api_status == 404


@pytest.mark.parametrize("status_code", [401, 429, 503])
def test_http_errors_are_safe(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    with _mocked_client(handler) as client, pytest.raises(AemetHttpError) as captured:
        client.fetch_product(MURCIA)

    message = str(captured.value)
    assert str(status_code) in message
    assert FAKE_SECRET not in message
    assert FAKE_SECRET not in repr(captured.value)


def test_timeout_is_converted_to_safe_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with _mocked_client(handler) as client, pytest.raises(AemetTransportError) as captured:
        client.fetch_product(MURCIA)

    assert FAKE_SECRET not in str(captured.value)


def test_ephemeral_data_download_failure_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/red/radar/regional/mu"):
            return httpx.Response(
                200,
                json={
                    "descripcion": "exito",
                    "estado": 200,
                    "datos": DATA_URL,
                    "metadatos": METADATA_URL,
                },
            )
        if request.url == httpx.URL(DATA_URL):
            return httpx.Response(503)
        raise AssertionError("No se debe solicitar metadatos tras fallar datos")

    with _mocked_client(handler) as client, pytest.raises(AemetHttpError) as captured:
        client.fetch_product(MURCIA)

    assert captured.value.status_code == 503
    assert "descarga de datos" in str(captured.value)


def test_does_not_follow_gateway_redirect_with_api_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"Location": "https://example.test/should-not-receive-key"},
            request=request,
        )

    with _mocked_client(handler) as client, pytest.raises(AemetHttpError) as captured:
        client.fetch_product(MURCIA)

    assert captured.value.status_code == 302
    assert len(requests) == 1


def test_does_not_follow_data_redirect() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/api/red/radar/regional/mu"):
            return httpx.Response(
                200,
                json={
                    "descripcion": "exito",
                    "estado": 200,
                    "datos": DATA_URL,
                    "metadatos": METADATA_URL,
                },
            )
        return httpx.Response(
            302,
            headers={"Location": "https://example.test/should-not-be-requested"},
            request=request,
        )

    with _mocked_client(handler) as client, pytest.raises(AemetHttpError) as captured:
        client.fetch_product(MURCIA)

    assert captured.value.status_code == 302
    assert len(requests) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"descripcion": "exito", "estado": 200},
        {"descripcion": "exito", "estado": "200", "datos": DATA_URL},
        {
            "descripcion": "exito",
            "estado": 200,
            "datos": "http://opendata.aemet.es/unsafe",
        },
        {
            "descripcion": "exito",
            "estado": 200,
            "datos": "https://example.test/unsafe",
        },
    ],
)
def test_rejects_invalid_gateway_payload(payload: dict[str, object]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    with _mocked_client(handler) as client, pytest.raises(AemetResponseError):
        client.fetch_product(MURCIA)


def _mocked_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AemetClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=transport,
        follow_redirects=True,
    )
    return AemetClient(api_key=FAKE_SECRET, http_client=http_client)
