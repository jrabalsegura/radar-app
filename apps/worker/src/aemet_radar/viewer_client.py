"""Cliente defensivo para la línea temporal PPI del visor oficial de AEMET."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import cast
from urllib.parse import quote

import httpx

from aemet_radar.errors import (
    AemetHttpError,
    AemetResponseError,
    AemetTransportError,
)

DEFAULT_VIEWER_BASE_URL = "https://www.aemet.es/es/api-eltiempo"
DEFAULT_VIEWER_MAX_IMAGE_BYTES = 20 * 1024 * 1024
VIEWER_PRODUCT = "PPI.Z_005_240"
VIEWER_SUBPRODUCT = "Z_005_240"
_FILENAME = re.compile(r"^(?P<site>[A-Z]{3})(?P<timestamp>\d{12})\.PPI\.Z_005_240\.png$")
_CAPTURED_HEADERS = (
    "cache-control",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
)

MapCoordinates = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]


@dataclass(frozen=True, slots=True)
class ViewerFrame:
    site_code: str
    radar_name: str
    observed_at: datetime
    file_name: str
    product: str
    subproduct: str


@dataclass(frozen=True, slots=True)
class ViewerTimeline:
    frames: tuple[ViewerFrame, ...]

    def frames_for(self, site_code: str) -> tuple[ViewerFrame, ...]:
        normalized = site_code.upper()
        return tuple(frame for frame in self.frames if frame.site_code == normalized)


@dataclass(frozen=True, slots=True)
class ViewerImage:
    frame: ViewerFrame
    content: bytes
    retrieved_at: datetime
    headers: dict[str, str]


class AemetViewerClient:
    """Descarga la cronología y los PNG públicos empleados por el visor de AEMET."""

    __slots__ = ("_client", "_max_image_bytes")

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_image_bytes: int = DEFAULT_VIEWER_MAX_IMAGE_BYTES,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._max_image_bytes = max_image_bytes
        self._client = http_client or httpx.Client(
            base_url=DEFAULT_VIEWER_BASE_URL,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "aemet-radar-worker/0.8"},
        )

    def __enter__(self) -> AemetViewerClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_timeline(self) -> ViewerTimeline:
        response = self._request(
            "/radar/timeline/PPI/PB",
            stage="consulta de la cronología PPI",
        )
        try:
            payload = json.loads(response.text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise AemetResponseError(
                "El visor de AEMET no devolvió una cronología JSON válida."
            ) from exc
        frames = _parse_timeline(payload)
        if not frames:
            raise AemetResponseError("La cronología PPI de AEMET está vacía.")
        return ViewerTimeline(frames=frames)

    def fetch_image(self, frame: ViewerFrame) -> ViewerImage:
        path = f"/radar/imagen-radar/PPI/{quote(frame.file_name, safe='')}"
        response, content = self._download(path, stage=f"descarga PPI de {frame.site_code}")
        return ViewerImage(
            frame=frame,
            content=content,
            retrieved_at=datetime.now(UTC),
            headers=_capture_headers(response.headers),
        )

    def fetch_bounds(self, frame: ViewerFrame) -> MapCoordinates:
        path = f"/radar/bounds-radar/PPI/{quote(frame.file_name, safe='')}"
        response = self._request(path, stage=f"límites PPI de {frame.site_code}")
        try:
            payload = json.loads(response.text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise AemetResponseError("El visor de AEMET no devolvió límites JSON válidos.") from exc
        return _parse_bounds(payload)

    def _request(self, path: str, *, stage: str) -> httpx.Response:
        try:
            response = self._client.get(path, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise AemetTransportError(stage) from exc
        if not 200 <= response.status_code < 300:
            raise AemetHttpError(stage, response.status_code)
        return response

    def _download(self, path: str, *, stage: str) -> tuple[httpx.Response, bytes]:
        try:
            with self._client.stream("GET", path, follow_redirects=False) as response:
                if not 200 <= response.status_code < 300:
                    raise AemetHttpError(stage, response.status_code)
                _ensure_content_length(response.headers, self._max_image_bytes)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self._max_image_bytes:
                        raise AemetResponseError("La imagen PPI supera el tamaño máximo permitido.")
                return response, bytes(content)
        except (AemetHttpError, AemetResponseError):
            raise
        except httpx.HTTPError as exc:
            raise AemetTransportError(stage) from exc


def _parse_timeline(payload: object) -> tuple[ViewerFrame, ...]:
    if not isinstance(payload, list):
        raise AemetResponseError("La cronología PPI no es una lista.")
    products = [
        item
        for item in payload
        if isinstance(item, dict) and item.get("Producto") == VIEWER_PRODUCT
    ]
    if len(products) != 1:
        raise AemetResponseError("La cronología no contiene un único producto PPI esperado.")
    elements = products[0].get("Elementos")
    if not isinstance(elements, list):
        raise AemetResponseError("El producto PPI no contiene una lista de observaciones.")

    by_observation: dict[tuple[str, datetime], ViewerFrame] = {}
    for raw in elements:
        if not isinstance(raw, dict):
            raise AemetResponseError("La cronología PPI contiene una observación no válida.")
        frame = _parse_frame(cast(Mapping[str, object], raw))
        key = (frame.site_code, frame.observed_at)
        previous = by_observation.get(key)
        if previous is not None and previous.file_name != frame.file_name:
            raise AemetResponseError("La cronología PPI contiene observaciones contradictorias.")
        by_observation[key] = frame
    return tuple(
        sorted(
            by_observation.values(),
            key=lambda frame: (frame.observed_at, frame.site_code, frame.file_name),
        )
    )


def _parse_frame(payload: Mapping[str, object]) -> ViewerFrame:
    file_name = _required_string(payload, "Nombre fichero")
    match = _FILENAME.fullmatch(file_name)
    if match is None:
        raise AemetResponseError("La cronología PPI contiene un nombre de fichero no válido.")
    product = _required_string(payload, "producto")
    subproduct = _required_string(payload, "subproducto")
    if product != "PPI" or subproduct != VIEWER_SUBPRODUCT:
        raise AemetResponseError("La observación no pertenece al PPI regional esperado.")

    try:
        file_time = datetime.strptime(match.group("timestamp"), "%y%m%d%H%M%S").replace(tzinfo=UTC)
        local_time = datetime.fromisoformat(_required_string(payload, "Fecha"))
    except ValueError as exc:
        raise AemetResponseError("La cronología PPI contiene una fecha no válida.") from exc
    if local_time.tzinfo is None:
        raise AemetResponseError("La fecha PPI no incluye zona horaria.")
    observed_at = local_time.astimezone(UTC)
    if observed_at != file_time:
        raise AemetResponseError("La fecha PPI no coincide con la fecha de su fichero.")

    return ViewerFrame(
        site_code=match.group("site"),
        radar_name=_required_string(payload, "Nombre radar"),
        observed_at=observed_at,
        file_name=file_name,
        product=product,
        subproduct=subproduct,
    )


def _parse_bounds(payload: object) -> MapCoordinates:
    if not isinstance(payload, list) or len(payload) != 4:
        raise AemetResponseError("Los límites PPI no contienen cuatro esquinas.")
    original: list[tuple[float, float]] = []
    for coordinate in payload:
        if not isinstance(coordinate, list) or len(coordinate) != 2:
            raise AemetResponseError("Una esquina PPI no es una coordenada.")
        longitude, latitude = coordinate
        if (
            not isinstance(longitude, (int, float))
            or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or isinstance(latitude, bool)
        ):
            raise AemetResponseError("Una esquina PPI contiene valores no numéricos.")
        lon = float(longitude)
        lat = float(latitude)
        if not math.isfinite(lon) or not math.isfinite(lat):
            raise AemetResponseError("Una esquina PPI contiene valores no finitos.")
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise AemetResponseError("Una esquina PPI queda fuera del planeta.")
        original.append((lon, lat))

    # AEMET: SE, NE, NW, SW. MapLibre: NW, NE, SE, SW.
    return (original[2], original[1], original[0], original[3])


def _required_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise AemetResponseError(f"La observación PPI no contiene {name}.")
    return value


def _capture_headers(headers: httpx.Headers) -> dict[str, str]:
    return {name: headers[name] for name in _CAPTURED_HEADERS if name in headers}


def _ensure_content_length(headers: httpx.Headers, maximum: int) -> None:
    value = headers.get("content-length")
    if value is None:
        return
    try:
        length = int(value)
    except ValueError as exc:
        raise AemetResponseError("AEMET devolvió un Content-Length PPI no válido.") from exc
    if length > maximum:
        raise AemetResponseError("La imagen PPI supera el tamaño máximo permitido.")
