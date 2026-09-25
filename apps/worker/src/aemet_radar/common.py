"""Utilidades compartidas para leer JSON local y coordenadas de MapLibre."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

# Esquinas NW, NE, SE y SW en el orden que espera una fuente ``image`` de MapLibre.
MapCoordinates = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]


def load_json_object(path: Path) -> dict[str, object] | None:
    """Devuelve el objeto JSON de ``path`` o ``None`` si falta o no es válido."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def parse_coordinate(value: object) -> tuple[float, float] | None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(
            isinstance(component, (int, float)) and not isinstance(component, bool)
            for component in value
        )
    ):
        return None
    return (float(value[0]), float(value[1]))


def parse_map_coordinates(value: object) -> MapCoordinates | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    result: list[tuple[float, float]] = []
    for coordinate in value:
        parsed = parse_coordinate(coordinate)
        if parsed is None:
            return None
        result.append(parsed)
    return cast(MapCoordinates, tuple(result))


def stored_viewer_coordinates(report_path: Path) -> MapCoordinates | None:
    """Lee las esquinas del visor guardadas en el informe de un original."""

    report = load_json_object(report_path)
    viewer = mapping(report.get("viewer")) if report is not None else {}
    return parse_map_coordinates(viewer.get("maplibreCoordinates"))
