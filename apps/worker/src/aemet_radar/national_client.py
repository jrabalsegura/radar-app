"""Cliente defensivo para la composición nacional del visor oficial de AEMET."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import cast
from urllib.parse import quote

import httpx

from aemet_radar.errors import (
    AemetHttpError,
    AemetResponseError,
    AemetTransportError,
)
from aemet_radar.viewer_client import (
    DEFAULT_VIEWER_BASE_URL,
    DEFAULT_VIEWER_MAX_IMAGE_BYTES,
    MapCoordinates,
)

NATIONAL_PRODUCT = "Composicion radar"
NATIONAL_REGION = "Penbal"
NATIONAL_PARAMETER = "compo"
NATIONAL_CADENCE_MINUTES = 10
NATIONAL_HISTORY_MINUTES = 230
_FILENAME = re.compile(r"^radw(?P<timestamp>\d{12})_3857\.png$")
_CAPTURED_HEADERS = (
    "cache-control",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
)


@dataclass(frozen=True, slots=True)
class NationalFrame:
    observed_at: datetime
    file_name: str
    product: str


@dataclass(frozen=True, slots=True)
class NationalTimeline:
    frames: tuple[NationalFrame, ...]
    expected_times: tuple[datetime, ...]

    def visible_frames(
        self,
        history_minutes: int = NATIONAL_HISTORY_MINUTES,
    ) -> tuple[NationalFrame, ...]:
        if not self.frames:
            return ()
        window_start = self.frames[-1].observed_at - timedelta(minutes=history_minutes)
        return tuple(frame for frame in self.frames if frame.observed_at >= window_start)


@dataclass(frozen=True, slots=True)
class NationalImage:
    frame: NationalFrame
    content: bytes
    retrieved_at: datetime
    headers: dict[str, str]


class AemetNationalClient:
    """Descarga la cronología y los PNG nacionales empleados por el visor."""

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
            headers={"User-Agent": "aemet-radar-worker/0.9"},
        )

    def __enter__(self) -> AemetNationalClient:
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

    def fetch_timeline(self) -> NationalTimeline:
        response = self._request(
            f"/radar/timeline/{NATIONAL_PARAMETER}/PB",
            stage="consulta de la cronología nacional",
        )
        try:
            payload = json.loads(response.text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise AemetResponseError(
                "El visor de AEMET no devolvió una cronología nacional JSON válida."
            ) from exc
        return _parse_timeline(payload)

    def fetch_image(self, frame: NationalFrame) -> NationalImage:
        path = f"/radar/imagen-radar/{NATIONAL_PARAMETER}/{quote(frame.file_name, safe='')}"
        response, content = self._download(path, stage="descarga de composición nacional")
        return NationalImage(
            frame=frame,
            content=content,
            retrieved_at=datetime.now(UTC),
            headers=_capture_headers(response.headers),
        )

    def fetch_bounds(self, frame: NationalFrame) -> MapCoordinates:
        path = f"/radar/bounds-radar/{NATIONAL_PARAMETER}/{quote(frame.file_name, safe='')}"
        response = self._request(path, stage="límites de composición nacional")
        try:
            payload = json.loads(response.text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise AemetResponseError(
                "El visor de AEMET no devolvió límites nacionales JSON válidos."
            ) from exc
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
                        raise AemetResponseError(
                            "La composición nacional supera el tamaño máximo permitido."
                        )
                return response, bytes(content)
        except (AemetHttpError, AemetResponseError):
            raise
        except httpx.HTTPError as exc:
            raise AemetTransportError(stage) from exc


def _parse_timeline(payload: object) -> NationalTimeline:
    if not isinstance(payload, list):
        raise AemetResponseError("La cronología nacional no es una lista.")
    products = [
        item
        for item in payload
        if isinstance(item, dict) and item.get("Producto") == NATIONAL_PRODUCT
    ]
    if len(products) != 1:
        raise AemetResponseError("La cronología no contiene una única composición nacional.")
    product = cast(dict[str, object], products[0])
    if product.get("Region") != NATIONAL_REGION:
        raise AemetResponseError("La composición nacional no pertenece a Penbal.")

    expected_raw = product.get("lineaTiempo")
    if not isinstance(expected_raw, list):
        raise AemetResponseError("La composición nacional no contiene una línea temporal.")
    expected_times = tuple(
        sorted(_parse_zoned_datetime(value, "línea temporal nacional") for value in expected_raw)
    )
    if not expected_times or len(expected_times) != len(set(expected_times)):
        raise AemetResponseError("La línea temporal nacional está vacía o duplicada.")
    cadence = timedelta(minutes=NATIONAL_CADENCE_MINUTES)
    if any(
        current - previous != cadence
        for previous, current in zip(expected_times, expected_times[1:])
    ):
        raise AemetResponseError("La línea temporal nacional no respeta la cadencia de 10 minutos.")

    elements = product.get("Elementos")
    if not isinstance(elements, list):
        raise AemetResponseError("La composición nacional no contiene una lista de observaciones.")
    expected_set = set(expected_times)
    by_time: dict[datetime, NationalFrame] = {}
    for raw in elements:
        if not isinstance(raw, dict):
            raise AemetResponseError("La composición nacional contiene una observación no válida.")
        frame = _parse_frame(cast(Mapping[str, object], raw))
        if frame.observed_at not in expected_set:
            raise AemetResponseError("Una observación nacional queda fuera de su línea temporal.")
        previous = by_time.get(frame.observed_at)
        if previous is not None and previous.file_name != frame.file_name:
            raise AemetResponseError(
                "La composición nacional contiene observaciones contradictorias."
            )
        by_time[frame.observed_at] = frame
    if not by_time:
        raise AemetResponseError("La cronología nacional no contiene observaciones.")
    return NationalTimeline(
        frames=tuple(sorted(by_time.values(), key=lambda frame: frame.observed_at)),
        expected_times=expected_times,
    )


def _parse_frame(payload: Mapping[str, object]) -> NationalFrame:
    file_name = _required_string(payload, "Nombre fichero")
    match = _FILENAME.fullmatch(file_name)
    if match is None:
        raise AemetResponseError("La composición nacional contiene un nombre de fichero no válido.")
    product = _required_string(payload, "producto")
    if product != NATIONAL_PRODUCT:
        raise AemetResponseError("La observación no pertenece a la composición nacional.")
    try:
        file_time = datetime.strptime(match.group("timestamp"), "%Y%m%d%H%M").replace(tzinfo=UTC)
    except ValueError as exc:
        raise AemetResponseError("El fichero nacional contiene una fecha no válida.") from exc
    observed_at = _parse_zoned_datetime(payload.get("Fecha"), "observación nacional")
    if observed_at != file_time:
        raise AemetResponseError("La fecha nacional no coincide con la fecha UTC de su fichero.")
    return NationalFrame(
        observed_at=observed_at,
        file_name=file_name,
        product=product,
    )


def _parse_zoned_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AemetResponseError(f"Falta la fecha de {label}.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AemetResponseError(f"La fecha de {label} no es válida.") from exc
    if parsed.tzinfo is None:
        raise AemetResponseError(f"La fecha de {label} no incluye zona horaria.")
    return parsed.astimezone(UTC)


def _parse_bounds(payload: object) -> MapCoordinates:
    if not isinstance(payload, list) or len(payload) != 4:
        raise AemetResponseError("Los límites nacionales no contienen cuatro esquinas.")
    original: list[tuple[float, float]] = []
    for coordinate in payload:
        if not isinstance(coordinate, list) or len(coordinate) != 2:
            raise AemetResponseError("Una esquina nacional no es una coordenada.")
        longitude, latitude = coordinate
        if (
            not isinstance(longitude, (int, float))
            or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or isinstance(latitude, bool)
        ):
            raise AemetResponseError("Una esquina nacional contiene valores no numéricos.")
        lon = float(longitude)
        lat = float(latitude)
        if not math.isfinite(lon) or not math.isfinite(lat):
            raise AemetResponseError("Una esquina nacional contiene valores no finitos.")
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise AemetResponseError("Una esquina nacional queda fuera del planeta.")
        original.append((lon, lat))
    # AEMET: SE, NE, NW, SW. MapLibre: NW, NE, SE, SW.
    return (original[2], original[1], original[0], original[3])


def _required_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise AemetResponseError(f"La observación nacional no contiene {name}.")
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
        raise AemetResponseError("AEMET devolvió un Content-Length nacional no válido.") from exc
    if length > maximum:
        raise AemetResponseError("La composición nacional supera el tamaño máximo permitido.")
