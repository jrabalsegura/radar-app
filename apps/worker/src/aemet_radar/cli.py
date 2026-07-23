"""Interfaz de línea de comandos del worker."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from dotenv import load_dotenv

from aemet_radar.client import DEFAULT_MAX_DOWNLOAD_BYTES, AemetClient
from aemet_radar.errors import AemetRadarError
from aemet_radar.models import FetchOutcome
from aemet_radar.products import PROVISIONAL_REGIONAL_PRODUCTS, SPIKE_PRODUCTS
from aemet_radar.service import IngestionService
from aemet_radar.settings import Settings
from aemet_radar.storage import ArchiveStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aemet-radar",
        description="Worker de ingesta de originales de Radar AEMET.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    fetch_once = subcommands.add_parser(
        "fetch-once",
        help="Consulta y archiva una vez los productos seleccionados.",
    )
    _add_common_network_arguments(fetch_once)
    fetch_once.add_argument(
        "--product",
        action="append",
        choices=tuple(SPIKE_PRODUCTS),
        dest="products",
        help="Producto a consultar; se puede repetir. Por defecto consulta los dos del spike.",
    )
    fetch_once.add_argument(
        "--max-bytes",
        type=_positive_int,
        default=DEFAULT_MAX_DOWNLOAD_BYTES,
        help="Tamaño máximo admitido por imagen.",
    )
    inventory = subcommands.add_parser(
        "check-inventory",
        help="Comprueba una vez los endpoints regionales sin descargar los GIF.",
    )
    _add_common_network_arguments(inventory)
    inventory.add_argument(
        "--delay",
        type=_non_negative_float,
        default=1.0,
        help="Espera entre endpoints en segundos (por defecto: 1).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    env_file = _as_path(arguments.env_file)
    load_dotenv(dotenv_path=env_file, override=False)

    try:
        settings = Settings.from_environment()
    except AemetRadarError as exc:
        _print_json({"status": "error", "error": _safe_error(exc)}, stream=sys.stderr)
        return 2

    if arguments.command == "fetch-once":
        return _run_fetch_once(arguments, settings)
    if arguments.command == "check-inventory":
        return _run_inventory_check(arguments, settings)
    parser.error("Comando no implementado.")


def _run_fetch_once(arguments: argparse.Namespace, settings: Settings) -> int:
    data_dir = _as_path(arguments.data_dir).resolve()
    selected_ids = _selected_product_ids(arguments.products)
    outcomes: list[FetchOutcome] = []
    results: list[dict[str, object]] = []

    with AemetClient(
        settings.api_key,
        timeout_seconds=float(arguments.timeout),
        max_download_bytes=int(arguments.max_bytes),
    ) as client:
        store = ArchiveStore(data_dir)
        service = IngestionService(client, store)
        for product_id in selected_ids:
            product = SPIKE_PRODUCTS[product_id]
            try:
                outcome = service.fetch_once(product)
            except AemetRadarError as exc:
                results.append(
                    {
                        "productId": product_id,
                        "status": "error",
                        "error": _safe_error(exc),
                    }
                )
            else:
                outcomes.append(outcome)
                results.append(outcome.to_dict(relative_to=data_dir))

        comparison_path: str | None = None
        if len(selected_ids) > 1:
            generated_at = datetime.now(UTC)
            path = store.write_comparison(
                generated_at=generated_at,
                products=results,
            )
            comparison_path = path.relative_to(data_dir).as_posix()

    _print_json(
        {
            "status": "ok" if len(outcomes) == len(selected_ids) else "partial-error",
            "results": results,
            "comparisonReport": comparison_path,
        }
    )
    return 0 if len(outcomes) == len(selected_ids) else 1


def _run_inventory_check(arguments: argparse.Namespace, settings: Settings) -> int:
    data_dir = _as_path(arguments.data_dir).resolve()
    results: list[dict[str, object]] = []
    error_count = 0
    delay = float(arguments.delay)

    with AemetClient(
        settings.api_key,
        timeout_seconds=float(arguments.timeout),
    ) as client:
        for index, product in enumerate(PROVISIONAL_REGIONAL_PRODUCTS):
            try:
                probe = client.probe_product(product)
            except AemetRadarError as exc:
                error_count += 1
                results.append(
                    {
                        "productId": product.id,
                        "label": product.label,
                        "aemetCode": product.aemet_code,
                        "status": "error",
                        "error": _safe_error(exc),
                    }
                )
            else:
                results.append(probe.to_dict())
            if index < len(PROVISIONAL_REGIONAL_PRODUCTS) - 1 and delay:
                time.sleep(delay)

    store = ArchiveStore(data_dir)
    generated_at = datetime.now(UTC)
    path = store.write_inventory(generated_at=generated_at, products=results)
    _print_json(
        {
            "status": "ok" if error_count == 0 else "partial-error",
            "results": results,
            "inventoryReport": path.relative_to(data_dir).as_posix(),
        }
    )
    return 0 if error_count == 0 else 1


def _add_common_network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directorio local de archivo (por defecto: data).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Archivo local opcional que carga variables sin sobrescribir el entorno.",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=15.0,
        help="Timeout HTTP por petición en segundos.",
    )


def _selected_product_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return tuple(SPIKE_PRODUCTS)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("products debe ser una lista de identificadores")
    return tuple(value)


def _as_path(value: object) -> Path:
    if not isinstance(value, Path):
        raise TypeError("Se esperaba una ruta.")
    return value


def _safe_error(error: AemetRadarError) -> dict[str, str]:
    return {"code": error.code, "message": str(error)}


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser cero o mayor")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return parsed


def _print_json(payload: object, *, stream: TextIO = sys.stdout) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    stream.write(serialized + "\n")
