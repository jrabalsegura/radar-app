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
from aemet_radar.errors import AemetRadarError, is_no_data_error
from aemet_radar.file_server import serve_files
from aemet_radar.georeferencing import georeference_overlay
from aemet_radar.health import HealthPublisher
from aemet_radar.history import scan_product_history
from aemet_radar.hybrid_service import HybridIngestionService
from aemet_radar.manifests import ManifestPublisher, select_history_frames
from aemet_radar.mask_calibration import discover_mask_samples
from aemet_radar.products import (
    PRODUCTS,
    REGIONAL_PRODUCTS,
    RadarProduct,
)
from aemet_radar.radar_catalog import DEFAULT_CATALOG_PATH, load_radar_catalog
from aemet_radar.reflectivity import (
    build_reviewed_dry_static_mask,
    build_static_mask,
    process_reflectivity_sample,
)
from aemet_radar.retry import RetryPolicy
from aemet_radar.runner import HistoryWorker, run_periodically
from aemet_radar.service import IngestionService
from aemet_radar.settings import OperationalSettings, Settings
from aemet_radar.storage import ArchiveStore
from aemet_radar.timeline_processing import RegionalTimelineProcessor
from aemet_radar.viewer_client import AemetViewerClient

DEFAULT_REFLECTIVITY_CONFIG = Path("config/palettes/regional-mu-v1.json")
DEFAULT_REFLECTIVITY_MASK = Path("config/masks/regional-mu-v1.png")
DEFAULT_GEOREFERENCING_CONFIG = Path("config/georeferencing/regional-mu-v1.json")


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
    fetch_once.add_argument(
        "--product-delay",
        type=_non_negative_float,
        default=None,
        help="Pausa entre productos regionales; por defecto usa el entorno.",
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
    run.add_argument(
        "--product-delay",
        type=_non_negative_float,
        default=None,
        help="Pausa entre productos regionales; por defecto usa el entorno.",
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

    georeference = subcommands.add_parser(
        "georeference-murcia",
        help="Reproyecta una capa RGBA de Murcia para mostrarla en MapLibre.",
    )
    georeference.add_argument(
        "input",
        type=Path,
        help="PNG RGBA 480×480 producido por analyze-reflectivity.",
    )
    georeference.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/debug/phase-4/regional-mu"),
        help="Directorio para el PNG Web Mercator y su informe.",
    )
    georeference.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_GEOREFERENCING_CONFIG,
        help="Calibración geográfica versionada de Murcia.",
    )

    build_mask = subcommands.add_parser(
        "build-reflectivity-mask",
        help="Genera una máscara estática regional desde varias muestras distintas.",
    )
    build_mask.add_argument(
        "samples",
        type=Path,
        nargs="+",
        help="Tres o más originales GIF distintos del mismo radar.",
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

    build_reviewed_mask = subcommands.add_parser(
        "build-reviewed-dry-mask",
        help="Genera una máscara desde un GIF cotejado con un PPI oficial vacío.",
    )
    build_reviewed_mask.add_argument(
        "sample",
        type=Path,
        help="Original GIF regional que contiene la cartografía fija.",
    )
    build_reviewed_mask.add_argument(
        "dry_reference",
        type=Path,
        help="PNG RGBA vacío descargado del visor PPI para el mismo radar y hora.",
    )
    build_reviewed_mask.add_argument(
        "--dry-reference-url",
        required=True,
        help="URL oficial exacta del PNG PPI cotejado.",
    )
    build_reviewed_mask.add_argument(
        "--observed-at",
        required=True,
        help="Hora UTC común del GIF y la referencia, en formato ISO 8601.",
    )
    build_reviewed_mask.add_argument(
        "--product",
        required=True,
        choices=tuple(product.id for product in REGIONAL_PRODUCTS),
        help="Radar regional al que pertenecen ambas imágenes.",
    )
    build_reviewed_mask.add_argument(
        "--output",
        type=Path,
        default=None,
        help="PNG binario; por defecto config/masks/<producto>-v1.png.",
    )
    build_reviewed_mask.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Informe JSON; por defecto usa el nombre de la máscara.",
    )
    build_reviewed_mask.add_argument(
        "--radar-config",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Catálogo regional versionado.",
    )

    build_radar_masks = subcommands.add_parser(
        "build-radar-masks",
        help="Genera máscaras específicas desde archivos de muestras regionales.",
    )
    build_radar_masks.add_argument(
        "--sample-root",
        type=Path,
        action="append",
        required=True,
        dest="sample_roots",
        help="Raíz data/ con raw/<producto>; se puede repetir.",
    )
    build_radar_masks.add_argument(
        "--output-dir",
        type=Path,
        default=Path("config/masks"),
        help="Directorio de máscaras e informes versionables.",
    )
    build_radar_masks.add_argument(
        "--minimum-samples",
        type=_positive_int,
        default=3,
        help="Mínimo de GIF distintos por radar (por defecto: 3).",
    )
    build_radar_masks.add_argument(
        "--minimum-span-hours",
        type=_positive_float,
        default=2.0,
        help="Separación mínima entre primera y última muestra (por defecto: 2 h).",
    )
    build_radar_masks.add_argument(
        "--radar-config",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Catálogo regional versionado.",
    )
    _add_product_argument(build_radar_masks)

    validate_radar = subcommands.add_parser(
        "validate-radar",
        help="Valida una muestra y genera previsualización geográfica por radar.",
    )
    validate_radar.add_argument(
        "input",
        type=Path,
        help="Original GIF del radar regional.",
    )
    validate_radar.add_argument(
        "--product",
        required=True,
        choices=tuple(product.id for product in REGIONAL_PRODUCTS),
        help="Radar regional al que pertenece la muestra.",
    )
    validate_radar.add_argument(
        "--radar-config",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Catálogo regional versionado.",
    )
    validate_radar.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/debug/phase-6/validation"),
        help="Directorio para informes y previsualizaciones.",
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
        if arguments.command == "georeference-murcia":
            return _run_georeferencing(arguments)
        if arguments.command == "build-reflectivity-mask":
            return _run_reflectivity_mask_build(arguments)
        if arguments.command == "build-reviewed-dry-mask":
            return _run_reviewed_dry_mask_build(arguments)
        if arguments.command == "build-radar-masks":
            return _run_radar_masks_build(arguments)
        if arguments.command == "validate-radar":
            return _run_radar_validation(arguments)
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
    operational = OperationalSettings.from_environment()
    data_dir = _as_path(arguments.data_dir).resolve()
    selected = _selected_products(arguments.products)
    product_delay = _value_or(
        arguments.product_delay,
        operational.product_delay_seconds,
    )
    error_count = 0
    results: list[dict[str, object]] = []

    catalog = load_radar_catalog(_as_path(arguments.radar_config))
    store = ArchiveStore(data_dir)
    with (
        AemetClient(
            settings.api_key,
            timeout_seconds=float(arguments.timeout),
            max_download_bytes=int(arguments.max_bytes),
        ) as client,
        AemetViewerClient(
            timeout_seconds=float(arguments.timeout),
            max_image_bytes=int(arguments.max_bytes),
        ) as viewer,
    ):
        service = HybridIngestionService(
            viewer,
            IngestionService(client, store),
            store,
            catalog=catalog,
        )
        service.begin_cycle()
        for product_index, product in enumerate(selected):
            try:
                outcome = service.fetch_once(product)
            except AemetRadarError as exc:
                if is_no_data_error(exc):
                    results.append(
                        {
                            "productId": product.id,
                            "status": "no-data",
                        }
                    )
                else:
                    error_count += 1
                    results.append(
                        {
                            "productId": product.id,
                            "status": "error",
                            "error": _safe_error(exc),
                        }
                    )
            else:
                results.append(outcome.to_dict(relative_to=data_dir))
            if product_index < len(selected) - 1 and product_delay > 0:
                time.sleep(product_delay)

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
            "status": "ok" if error_count == 0 else "partial-error",
            "results": results,
            "comparisonReport": comparison_path,
        }
    )
    return 0 if error_count == 0 else 1


def _run_inventory_check(arguments: argparse.Namespace, settings: Settings) -> int:
    data_dir = _as_path(arguments.data_dir).resolve()
    products = load_radar_catalog(_as_path(arguments.radar_config)).products
    results: list[dict[str, object]] = []
    error_count = 0
    delay = float(arguments.delay)

    with AemetClient(
        settings.api_key,
        timeout_seconds=float(arguments.timeout),
    ) as client:
        for index, product in enumerate(products):
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
            if index < len(products) - 1 and delay:
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

    catalog = load_radar_catalog(_as_path(arguments.radar_config))
    store = ArchiveStore(data_dir)
    with (
        AemetClient(
            settings.api_key,
            timeout_seconds=float(arguments.timeout),
            max_download_bytes=int(arguments.max_bytes),
        ) as client,
        AemetViewerClient(
            timeout_seconds=float(arguments.timeout),
            max_image_bytes=int(arguments.max_bytes),
        ) as viewer,
    ):
        worker = HistoryWorker(
            HybridIngestionService(
                viewer,
                IngestionService(client, store),
                store,
                catalog=catalog,
            ),
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
            timeline_processor=_timeline_processor(
                data_dir,
                _as_path(arguments.radar_config),
            ),
            product_delay_seconds=_value_or(
                arguments.product_delay,
                operational.product_delay_seconds,
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
    history_hours = _value_or(arguments.history_hours, operational.history_hours)
    timeline_processor = _timeline_processor(
        data_dir,
        _as_path(arguments.radar_config),
    )
    publisher = ManifestPublisher(
        data_dir,
        history_hours=history_hours,
        image_resolver=timeline_processor.frame_image,
        radar_metadata_resolver=timeline_processor.radar_metadata,
    )
    results = []
    for product in selected:
        scan = scan_product_history(data_dir, product)
        timeline_processor.ensure_frames(
            product,
            select_history_frames(scan.frames, history_hours),
        )
        results.append(publisher.rebuild_product(product, generated_at=generated_at))
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


def _run_georeferencing(arguments: argparse.Namespace) -> int:
    result = georeference_overlay(
        _as_path(arguments.input).resolve(),
        config_path=_as_path(arguments.config).resolve(),
        output_dir=_as_path(arguments.output_dir).resolve(),
    )
    output = result.report.get("output")
    calibration = result.report.get("calibration")
    _print_json(
        {
            "status": "ok",
            "processor": result.report["processor"],
            "image": result.image_path.as_posix(),
            "report": result.report_path.as_posix(),
            "dimensions": (
                {
                    "width": output.get("width"),
                    "height": output.get("height"),
                }
                if isinstance(output, dict)
                else None
            ),
            "meanErrorKilometres": (
                calibration.get("meanErrorKilometres") if isinstance(calibration, dict) else None
            ),
            "maximumErrorKilometres": (
                calibration.get("maximumErrorKilometres") if isinstance(calibration, dict) else None
            ),
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


def _run_reviewed_dry_mask_build(arguments: argparse.Namespace) -> int:
    product_id = str(arguments.product)
    definition = load_radar_catalog(_as_path(arguments.radar_config)).definition_for(product_id)
    output_value = arguments.output
    output_path = (
        output_value.resolve()
        if isinstance(output_value, Path)
        else Path("config/masks").resolve() / f"{product_id}-v1.png"
    )
    report_value = arguments.report
    report_path = report_value.resolve() if isinstance(report_value, Path) else None
    result = build_reviewed_dry_static_mask(
        _as_path(arguments.sample).resolve(),
        dry_reference_path=_as_path(arguments.dry_reference).resolve(),
        dry_reference_url=str(arguments.dry_reference_url),
        observed_at=str(arguments.observed_at),
        config_path=definition.reflectivity_config_path,
        mask_path=output_path,
        report_path=report_path,
        product_id=product_id,
        expected_site_code=definition.site_code,
    )
    _print_json(
        {
            "status": "ok",
            "processor": result.report["processor"],
            "mask": result.mask_path.as_posix(),
            "report": result.report_path.as_posix(),
            "algorithm": result.report["algorithm"],
            "excludedPixels": result.report["excludedPixels"],
        }
    )
    return 0


def _run_radar_masks_build(arguments: argparse.Namespace) -> int:
    roots = arguments.sample_roots
    if not isinstance(roots, list) or not all(isinstance(item, Path) for item in roots):
        raise TypeError("sample_roots debe ser una lista de rutas")
    catalog = load_radar_catalog(_as_path(arguments.radar_config))
    selected_ids = (
        set(arguments.products)
        if isinstance(arguments.products, list)
        else {item.product.id for item in catalog.definitions}
    )
    output_dir = _as_path(arguments.output_dir).resolve()
    minimum_samples = int(arguments.minimum_samples)
    minimum_span_hours = float(arguments.minimum_span_hours)
    results: list[dict[str, object]] = []

    for definition in catalog.definitions:
        product_id = definition.product.id
        if product_id not in selected_ids:
            continue
        inventory = discover_mask_samples(
            product_id,
            tuple(item.resolve() for item in roots),
        )
        span_hours = inventory.span_hours
        reported_span_hours = round(span_hours, 6) if span_hours is not None else None
        if len(inventory.samples) < minimum_samples:
            results.append(
                {
                    "productId": product_id,
                    "status": "awaiting-samples",
                    "distinctSamples": len(inventory.samples),
                    "requiredSamples": minimum_samples,
                    "observationWindowHours": reported_span_hours,
                }
            )
            continue
        if span_hours is None or span_hours < minimum_span_hours:
            results.append(
                {
                    "productId": product_id,
                    "status": "awaiting-span",
                    "distinctSamples": len(inventory.samples),
                    "observationWindowHours": reported_span_hours,
                    "requiredWindowHours": minimum_span_hours,
                }
            )
            continue

        result = build_static_mask(
            tuple(sample.path for sample in inventory.samples),
            config_path=definition.reflectivity_config_path,
            mask_path=output_dir / f"{product_id}-v1.png",
            report_path=output_dir / f"{product_id}-v1.json",
            product_id=product_id,
            source_evidence=inventory.source_evidence,
            observation_span_hours=reported_span_hours,
        )
        results.append(
            {
                "productId": product_id,
                "status": "built",
                "distinctSamples": result.report["distinctSamples"],
                "observationWindowHours": reported_span_hours,
                "excludedPixels": result.report["excludedPixels"],
                "mask": result.mask_path.as_posix(),
                "report": result.report_path.as_posix(),
            }
        )

    built = sum(item["status"] == "built" for item in results)
    _print_json(
        {
            "status": "ok",
            "built": built,
            "awaitingEvidence": len(results) - built,
            "results": results,
        }
    )
    return 0


def _run_radar_validation(arguments: argparse.Namespace) -> int:
    product_id = str(arguments.product)
    product = PRODUCTS[product_id]
    output_dir = _as_path(arguments.output_dir).resolve()
    processor = RegionalTimelineProcessor(
        output_dir,
        catalog=load_radar_catalog(_as_path(arguments.radar_config)),
    )
    report = processor.validate_sample(
        product,
        _as_path(arguments.input).resolve(),
        output_dir=output_dir,
    )
    _print_json(
        {
            "status": report["status"],
            "productId": product.id,
            "report": (output_dir / "validation.json").as_posix(),
            "overlay": (output_dir / str(report["overlay"])).as_posix(),
            "calibrationPreview": (output_dir / str(report["calibrationPreview"])).as_posix(),
        }
    )
    return 0


def _timeline_processor(
    data_dir: Path,
    catalog_path: Path,
) -> RegionalTimelineProcessor:
    return RegionalTimelineProcessor(
        data_dir,
        catalog=load_radar_catalog(catalog_path),
    )


def _add_product_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--product",
        action="append",
        choices=tuple(PRODUCTS),
        dest="products",
        help="Producto; se puede repetir. Por defecto usa los 15 radares regionales.",
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
    parser.add_argument(
        "--radar-config",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Catálogo regional versionado (por defecto: config/radars.yaml).",
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
        return REGIONAL_PRODUCTS
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("products debe ser una lista de identificadores")
    return tuple(PRODUCTS[product_id] for product_id in value)


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
