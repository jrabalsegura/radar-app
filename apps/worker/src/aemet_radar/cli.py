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
from aemet_radar.file_server import serve_files
from aemet_radar.health import HealthPublisher
from aemet_radar.manifests import ManifestPublisher
from aemet_radar.models import FetchOutcome
from aemet_radar.products import (
    PROVISIONAL_REGIONAL_PRODUCTS,
    SPIKE_PRODUCTS,
    RadarProduct,
)
from aemet_radar.reflectivity import (
    build_static_mask,
    process_reflectivity_sample,
)
from aemet_radar.retry import RetryPolicy
from aemet_radar.runner import HistoryWorker, run_periodically
from aemet_radar.service import IngestionService
from aemet_radar.settings import OperationalSettings, Settings
from aemet_radar.storage import ArchiveStore

DEFAULT_REFLECTIVITY_CONFIG = Path("config/palettes/regional-mu-v1.json")
DEFAULT_REFLECTIVITY_MASK = Path("config/masks/regional-mu-v1.png")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aemet-radar",
        description="Worker de ingesta e historial de Radar AEMET.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    fetch_once = subcommands.add_parser(
        "fetch-once",
        help="Consulta y archiva una vez los productos seleccionados.",
    )
    _add_common_network_arguments(fetch_once)
    _add_product_argument(fetch_once)
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

    run = subcommands.add_parser(
        "run",
        help="Ejecuta el ciclo periódico de ingesta, retención y publicación.",
    )
    _add_common_network_arguments(run)
    _add_product_argument(run)
    run.add_argument(
        "--max-bytes",
        type=_positive_int,
        default=DEFAULT_MAX_DOWNLOAD_BYTES,
        help="Tamaño máximo admitido por imagen.",
    )
    run.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=None,
        help="Segundos entre inicios de ciclo; por defecto usa el entorno.",
    )
    run.add_argument(
        "--retry-attempts",
        type=_positive_int,
        default=None,
        help="Número máximo de intentos por producto.",
    )
    run.add_argument(
        "--retry-backoff",
        type=_non_negative_float,
        default=None,
        help="Espera inicial de reintento en segundos.",
    )
    run.add_argument(
        "--retention-hours",
        type=_positive_float,
        default=None,
        help="Retención de originales en horas.",
    )
    run.add_argument(
        "--history-hours",
        type=_positive_float,
        default=None,
        help="Ventana publicada en horas.",
    )
    run.add_argument(
        "--cycles",
        type=_positive_int,
        default=None,
        help="Finaliza tras N ciclos; sin este argumento se ejecuta continuamente.",
    )

    rebuild = subcommands.add_parser(
        "rebuild-manifests",
        help="Reconstruye manifiestos y health.json exclusivamente desde disco.",
    )
    _add_data_arguments(rebuild)
    _add_product_argument(rebuild)
    rebuild.add_argument(
        "--history-hours",
        type=_positive_float,
        default=None,
        help="Ventana publicada en horas.",
    )

    serve = subcommands.add_parser(
        "serve-files",
        help="Sirve data/ localmente sin habilitar listado de directorios.",
    )
    _add_data_arguments(serve)
    serve.add_argument("--host", default="127.0.0.1", help="Interfaz local de escucha.")
    serve.add_argument(
        "--port",
        type=_port,
        default=8000,
        help="Puerto HTTP local (por defecto: 8000).",
    )

    analyze = subcommands.add_parser(
        "analyze-reflectivity",
        help="Regenera las salidas de extracción de una muestra GIF de Murcia.",
    )
    analyze.add_argument("input", type=Path, help="Original GIF regional de Murcia.")
    analyze.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/debug/phase-3/regional-mu"),
        help="Directorio para PNG e informe JSON de depuración.",
    )
    analyze.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_REFLECTIVITY_CONFIG,
        help="Configuración versionada de paleta y recorte.",
    )
    analyze.add_argument(
        "--mask",
        type=Path,
        default=DEFAULT_REFLECTIVITY_MASK,
        help="Máscara estática versionada.",
    )

    build_mask = subcommands.add_parser(
        "build-reflectivity-mask",
        help="Genera la máscara estática de Murcia desde varias muestras distintas.",
    )
    build_mask.add_argument(
        "samples",
        type=Path,
        nargs="+",
        help="Tres o más originales GIF regionales de Murcia.",
    )
    build_mask.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REFLECTIVITY_MASK,
        help="PNG binario de máscara que se debe generar.",
    )
    build_mask.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Informe JSON; por defecto usa el nombre de la máscara.",
    )
    build_mask.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_REFLECTIVITY_CONFIG,
        help="Configuración versionada de paleta y recorte.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    env_file = getattr(arguments, "env_file", None)
    if isinstance(env_file, Path):
        load_dotenv(dotenv_path=env_file, override=False)

    try:
        if arguments.command == "fetch-once":
            return _run_fetch_once(arguments, Settings.from_environment())
        if arguments.command == "check-inventory":
            return _run_inventory_check(arguments, Settings.from_environment())
        if arguments.command == "run":
            return _run_history(arguments, Settings.from_environment())
        if arguments.command == "rebuild-manifests":
            return _run_rebuild(arguments)
        if arguments.command == "serve-files":
            return _run_file_server(arguments)
        if arguments.command == "analyze-reflectivity":
            return _run_reflectivity_analysis(arguments)
        if arguments.command == "build-reflectivity-mask":
            return _run_reflectivity_mask_build(arguments)
    except AemetRadarError as exc:
        _print_json({"status": "error", "error": _safe_error(exc)}, stream=sys.stderr)
        return 2
    except (OSError, ValueError):
        _print_json(
            {
                "status": "error",
                "error": {
                    "code": "local_operation_error",
                    "message": "No se pudo completar la operación local de forma segura.",
                },
            },
            stream=sys.stderr,
        )
        return 2
    parser.error("Comando no implementado.")


def _run_fetch_once(arguments: argparse.Namespace, settings: Settings) -> int:
    data_dir = _as_path(arguments.data_dir).resolve()
    selected = _selected_products(arguments.products)
    outcomes: list[FetchOutcome] = []
    results: list[dict[str, object]] = []

    with AemetClient(
        settings.api_key,
        timeout_seconds=float(arguments.timeout),
        max_download_bytes=int(arguments.max_bytes),
    ) as client:
        store = ArchiveStore(data_dir)
        service = IngestionService(client, store)
        for product in selected:
            try:
                outcome = service.fetch_once(product)
            except AemetRadarError as exc:
                results.append(
                    {
                        "productId": product.id,
                        "status": "error",
                        "error": _safe_error(exc),
                    }
                )
            else:
                outcomes.append(outcome)
                results.append(outcome.to_dict(relative_to=data_dir))

        comparison_path: str | None = None
        if len(selected) > 1:
            generated_at = datetime.now(UTC)
            path = store.write_comparison(
                generated_at=generated_at,
                products=results,
            )
            comparison_path = path.relative_to(data_dir).as_posix()

    _print_json(
        {
            "status": "ok" if len(outcomes) == len(selected) else "partial-error",
            "results": results,
            "comparisonReport": comparison_path,
        }
    )
    return 0 if len(outcomes) == len(selected) else 1


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


def _run_history(arguments: argparse.Namespace, settings: Settings) -> int:
    operational = OperationalSettings.from_environment()
    data_dir = _as_path(arguments.data_dir).resolve()
    selected = _selected_products(arguments.products)
    retry_policy = RetryPolicy(
        max_attempts=_value_or(arguments.retry_attempts, operational.retry_attempts),
        initial_backoff_seconds=_value_or(
            arguments.retry_backoff,
            operational.retry_backoff_seconds,
        ),
    )
    had_error = False

    with AemetClient(
        settings.api_key,
        timeout_seconds=float(arguments.timeout),
        max_download_bytes=int(arguments.max_bytes),
    ) as client:
        worker = HistoryWorker(
            IngestionService(client, ArchiveStore(data_dir)),
            data_dir=data_dir,
            products=selected,
            retry_policy=retry_policy,
            retention_hours=_value_or(
                arguments.retention_hours,
                operational.retention_hours,
            ),
            history_hours=_value_or(
                arguments.history_hours,
                operational.history_hours,
            ),
        )

        def execute_cycle() -> None:
            nonlocal had_error
            result = worker.run_cycle()
            had_error = had_error or not result.successful
            _print_json(result.to_dict())

        try:
            run_periodically(
                execute_cycle,
                interval_seconds=_value_or(
                    arguments.poll_interval,
                    operational.poll_interval_seconds,
                ),
                max_cycles=arguments.cycles,
            )
        except KeyboardInterrupt:
            _print_json({"status": "stopped"}, stream=sys.stderr)
            return 130
    return 1 if had_error else 0


def _run_rebuild(arguments: argparse.Namespace) -> int:
    operational = OperationalSettings.from_environment()
    data_dir = _as_path(arguments.data_dir).resolve()
    selected = _selected_products(arguments.products)
    generated_at = datetime.now(UTC)
    publisher = ManifestPublisher(
        data_dir,
        history_hours=_value_or(arguments.history_hours, operational.history_hours),
    )
    results = [
        publisher.rebuild_product(product, generated_at=generated_at) for product in selected
    ]
    index_path = publisher.rebuild_index(selected, generated_at=generated_at)
    health_path = HealthPublisher(data_dir, publisher).publish(
        selected,
        generated_at=generated_at,
    )
    _print_json(
        {
            "status": "ok",
            "manifests": [
                {
                    "productId": result.product_id,
                    "path": result.path.relative_to(data_dir).as_posix(),
                    "publishedFrames": _list_length(result.payload, "frames"),
                    "invalidReports": len(result.scan.issues),
                }
                for result in results
            ],
            "index": index_path.relative_to(data_dir).as_posix(),
            "health": health_path.relative_to(data_dir).as_posix(),
        }
    )
    return 0


def _run_file_server(arguments: argparse.Namespace) -> int:
    data_dir = _as_path(arguments.data_dir).resolve()
    host = str(arguments.host)
    port = int(arguments.port)
    _print_json(
        {
            "status": "serving",
            "root": data_dir.as_posix(),
            "url": f"http://{host}:{port}/radar/index.json",
            "healthUrl": f"http://{host}:{port}/status/health.json",
        }
    )
    try:
        serve_files(data_dir, host=host, port=port)
    except KeyboardInterrupt:
        return 130
    return 0


def _run_reflectivity_analysis(arguments: argparse.Namespace) -> int:
    result = process_reflectivity_sample(
        _as_path(arguments.input).resolve(),
        config_path=_as_path(arguments.config).resolve(),
        static_mask_path=_as_path(arguments.mask).resolve(),
        output_dir=_as_path(arguments.output_dir).resolve(),
    )
    statistics = result.report.get("statistics")
    reflectivity_pixels = (
        statistics.get("reflectivityPixels") if isinstance(statistics, dict) else None
    )
    _print_json(
        {
            "status": "ok",
            "processor": result.report["processor"],
            "report": result.report_path.as_posix(),
            "reflectivityPixels": reflectivity_pixels,
        }
    )
    return 0


def _run_reflectivity_mask_build(arguments: argparse.Namespace) -> int:
    samples = arguments.samples
    if not isinstance(samples, list) or not all(isinstance(item, Path) for item in samples):
        raise TypeError("samples debe ser una lista de rutas")
    report_value = arguments.report
    report_path = report_value.resolve() if isinstance(report_value, Path) else None
    result = build_static_mask(
        tuple(item.resolve() for item in samples),
        config_path=_as_path(arguments.config).resolve(),
        mask_path=_as_path(arguments.output).resolve(),
        report_path=report_path,
    )
    _print_json(
        {
            "status": "ok",
            "processor": result.report["processor"],
            "mask": result.mask_path.as_posix(),
            "report": result.report_path.as_posix(),
            "distinctSamples": result.report["distinctSamples"],
            "excludedPixels": result.report["excludedPixels"],
        }
    )
    return 0


def _add_product_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--product",
        action="append",
        choices=tuple(SPIKE_PRODUCTS),
        dest="products",
        help="Producto; se puede repetir. Por defecto usa Murcia y nacional.",
    )


def _add_data_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directorio local de archivo y publicación (por defecto: data).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Archivo local opcional que carga variables sin sobrescribir el entorno.",
    )


def _add_common_network_arguments(parser: argparse.ArgumentParser) -> None:
    _add_data_arguments(parser)
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=15.0,
        help="Timeout HTTP por petición en segundos.",
    )


def _selected_products(value: object) -> tuple[RadarProduct, ...]:
    if value is None:
        return tuple(SPIKE_PRODUCTS.values())
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("products debe ser una lista de identificadores")
    return tuple(SPIKE_PRODUCTS[product_id] for product_id in value)


def _as_path(value: object) -> Path:
    if not isinstance(value, Path):
        raise TypeError("Se esperaba una ruta.")
    return value


def _value_or[T](value: T | None, default: T) -> T:
    return default if value is None else value


def _list_length(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    return len(value) if isinstance(value, list) else 0


def _safe_error(error: AemetRadarError) -> dict[str, object]:
    payload: dict[str, object] = {"code": error.code, "message": str(error)}
    details = error.safe_details()
    if details:
        payload["details"] = details
    return payload


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


def _port(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 65_535:
        raise argparse.ArgumentTypeError("debe estar entre 0 y 65535")
    return parsed


def _print_json(payload: object, *, stream: TextIO | None = None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    destination = sys.stdout if stream is None else stream
    destination.write(serialized + "\n")
