"""Cliente defensivo para la composición nacional del visor oficial de AEMET."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import quote

from aemet_radar.common import MapCoordinates
from aemet_radar.errors import AemetResponseError
from aemet_radar.viewer_client import ViewerHttpClient

NATIONAL_PRODUCT = "Composicion radar"
NATIONAL_REGION = "Penbal"
NATIONAL_PARAMETER = "compo"
NATIONAL_CADENCE_MINUTES = 10
NATIONAL_HISTORY_MINUTES = 230
_FILENAME = re.compile(r"^radw(?P<timestamp>\d{12})_3857\.png$")


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


class AemetNationalClient(ViewerHttpClient):
    """Descarga la cronología y los PNG nacionales empleados por el visor."""

    __slots__ = ()

    def fetch_timeline(self) -> NationalTimeline:
        return _parse_timeline(
            self._get_json(
                f"/radar/timeline/{NATIONAL_PARAMETER}/PB",
                stage="consulta de la cronología nacional",
                invalid_message=(
                    "El visor de AEMET no devolvió una cronología nacional JSON válida."
                ),
            )
        )

    def fetch_image(self, frame: NationalFrame) -> NationalImage:
        content, headers = self._download(
            f"/radar/imagen-radar/{NATIONAL_PARAMETER}/{quote(frame.file_name, safe='')}",
            stage="descarga de composición nacional",
        )
        return NationalImage(
            frame=frame,
            content=content,
            retrieved_at=datetime.now(UTC),
            headers=headers,
        )

    def fetch_bounds(self, frame: NationalFrame) -> MapCoordinates:
        return self._fetch_bounds(
            f"/radar/bounds-radar/{NATIONAL_PARAMETER}/{quote(frame.file_name, safe='')}",
            stage="límites de composición nacional",
        )


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


def _required_string(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise AemetResponseError(f"La observación nacional no contiene {name}.")
    return value
