"""Cliente HTTP mínimo y seguro para AEMET OpenData."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import PurePosixPath
from types import TracebackType
from typing import cast
from urllib.parse import urlsplit

import httpx

from aemet_radar.errors import (
    AemetApiStatusError,
    AemetHttpError,
    AemetResponseError,
    AemetTransportError,
)
from aemet_radar.models import DownloadedProduct, MetadataDownload, ProductProbe
from aemet_radar.products import RadarProduct

DEFAULT_BASE_URL = "https://opendata.aemet.es/opendata"
DEFAULT_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
_ALLOWED_DOWNLOAD_HOSTS = frozenset({"opendata.aemet.es"})
_CAPTURED_HEADERS = (
    "cache-control",
    "content-disposition",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
)


class AemetClient:
    """Consulta la pasarela y descarga inmediatamente el recurso efímero."""

    __slots__ = (
        "_api_key",
        "_client",
        "_max_download_bytes",
    )

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_download_bytes = max_download_bytes
        self._client = http_client or httpx.Client(
            base_url=DEFAULT_BASE_URL,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "aemet-radar-worker/0.8"},
        )

    def __enter__(self) -> AemetClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return "AemetClient(api_key=<redacted>)"

    def close(self) -> None:
        self._client.close()

    def fetch_product(self, product: RadarProduct) -> DownloadedProduct:
        gateway_response = self._request(
            product.endpoint,
            stage=f"consulta de {product.id}",
            headers={"api_key": self._api_key},
        )
        gateway_payload = _read_gateway_payload(gateway_response)
        data_url = _required_https_url(gateway_payload, "datos")
        metadata_url = _optional_https_url(gateway_payload, "metadatos")

        data_response, content = self._download_data(data_url, product.id)
        retrieved_at = datetime.now(UTC)
        metadata = self._download_metadata(metadata_url, product.id)

        return DownloadedProduct(
            product=product,
            content=content,
            retrieved_at=retrieved_at,
            resource_name=PurePosixPath(urlsplit(data_url).path).name,
            gateway_status=gateway_response.status_code,
            gateway_headers=_capture_headers(gateway_response.headers),
            data_status=data_response.status_code,
            data_headers=_capture_headers(data_response.headers),
            metadata=metadata,
        )

    def probe_product(self, product: RadarProduct) -> ProductProbe:
        """Comprueba el endpoint estable sin descargar el recurso de datos."""

        gateway_response = self._request(
            product.endpoint,
            stage=f"comprobación de {product.id}",
            headers={"api_key": self._api_key},
        )
        payload, state = _read_gateway_object(gateway_response)
        if state != 200:
            return ProductProbe(
                product_id=product.id,
                label=product.label,
                aemet_code=product.aemet_code,
                status="unavailable",
                http_status=gateway_response.status_code,
                api_status=state,
                has_data_url=False,
                has_metadata_url=False,
                headers=_capture_headers(gateway_response.headers),
            )

        data_url = _required_https_url(payload, "datos")
        metadata_url = _optional_https_url(payload, "metadatos")
        return ProductProbe(
            product_id=product.id,
            label=product.label,
            aemet_code=product.aemet_code,
            status="available",
            http_status=gateway_response.status_code,
            api_status=state,
            has_data_url=bool(data_url),
            has_metadata_url=metadata_url is not None,
            headers=_capture_headers(gateway_response.headers),
        )

    def _request(
        self,
        url: str,
        *,
        stage: str,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = self._client.get(url, headers=headers, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise AemetTransportError(stage) from exc
        _ensure_success(response, stage)
        return response

    def _download_data(self, data_url: str, product_id: str) -> tuple[httpx.Response, bytes]:
        stage = f"descarga de datos de {product_id}"
        try:
            with self._client.stream("GET", data_url, follow_redirects=False) as response:
                _ensure_success(response, stage)
                _ensure_content_length(response.headers, self._max_download_bytes)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self._max_download_bytes:
                        raise AemetResponseError(
                            "El recurso de datos supera el tamaño máximo permitido."
                        )
                return response, bytes(content)
        except AemetResponseError:
            raise
        except httpx.HTTPError as exc:
            raise AemetTransportError(stage) from exc

    def _download_metadata(
        self,
        metadata_url: str | None,
        product_id: str,
    ) -> MetadataDownload:
        if metadata_url is None:
            return MetadataDownload(status="missing", headers={}, payload=None)

        try:
            response = self._request(
                metadata_url,
                stage=f"descarga de metadatos de {product_id}",
            )
            payload = _read_json(response)
        except (AemetHttpError, AemetResponseError, AemetTransportError) as exc:
            return MetadataDownload(
                status="error",
                headers={},
                payload=None,
                error_code=exc.code,
            )
        except (UnicodeDecodeError, ValueError):
            return MetadataDownload(
                status="error",
                headers=_capture_headers(response.headers),
                payload=None,
                error_code="invalid_metadata_json",
            )

        return MetadataDownload(
            status="ok",
            headers=_capture_headers(response.headers),
            payload=payload,
        )


def _ensure_success(response: httpx.Response, stage: str) -> None:
    if not 200 <= response.status_code < 300:
        raise AemetHttpError(stage, response.status_code)


def _read_gateway_payload(response: httpx.Response) -> dict[str, object]:
    payload, state = _read_gateway_object(response)
    if state != 200:
        raise AemetApiStatusError(state)
    return payload


def _read_gateway_object(response: httpx.Response) -> tuple[dict[str, object], int]:
    try:
        raw_payload = _read_json(response)
    except (UnicodeDecodeError, ValueError) as exc:
        raise AemetResponseError("AEMET no devolvió JSON válido en la consulta inicial.") from exc

    if not isinstance(raw_payload, dict):
        raise AemetResponseError("La respuesta inicial de AEMET no es un objeto JSON.")

    payload = cast(dict[str, object], raw_payload)
    state = payload.get("estado")
    if not isinstance(state, int):
        raise AemetResponseError("La respuesta inicial no contiene un estado entero.")
    return payload, state


def _read_json(response: httpx.Response) -> object:
    return cast(object, json.loads(response.text))


def _required_https_url(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise AemetResponseError(f"La respuesta inicial no contiene el campo {field}.")
    return _validate_download_url(value, field)


def _optional_https_url(payload: Mapping[str, object], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise AemetResponseError(f"El campo {field} no contiene una URL válida.")
    return _validate_download_url(value, field)


def _validate_download_url(url: str, field: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_DOWNLOAD_HOSTS:
        raise AemetResponseError(f"El campo {field} apunta fuera del origen permitido.")
    if parsed.username is not None or parsed.password is not None:
        raise AemetResponseError(f"El campo {field} contiene credenciales no permitidas.")
    return url


def _capture_headers(headers: httpx.Headers) -> dict[str, str]:
    return {name: headers[name] for name in _CAPTURED_HEADERS if name in headers}


def _ensure_content_length(headers: httpx.Headers, maximum: int) -> None:
    value = headers.get("content-length")
    if value is None:
        return
    try:
        length = int(value)
    except ValueError as exc:
        raise AemetResponseError("AEMET devolvió un Content-Length no válido.") from exc
    if length > maximum:
        raise AemetResponseError("El recurso de datos supera el tamaño máximo permitido.")
