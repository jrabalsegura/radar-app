"""Ciclo de ingesta, retención y publicación de la Fase 2."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aemet_radar.diagnostics import FailureRecorder
from aemet_radar.errors import AemetRadarError, DownloadValidationError, is_no_data_error
from aemet_radar.health import HealthPublisher, PollObservation
from aemet_radar.history import isoformat_utc, scan_product_history
from aemet_radar.manifests import ManifestPublisher, select_history_frames
from aemet_radar.models import FetchOutcome
from aemet_radar.products import RadarProduct
from aemet_radar.retention import RetentionManager
from aemet_radar.retry import RetryPolicy, call_with_retry
from aemet_radar.service import IngestionService
from aemet_radar.timeline_processing import RegionalTimelineProcessor


@dataclass(frozen=True, slots=True)
class ProductCycleResult:
    product_id: str
    status: str
    attempts: int
    removed_frames: int
    published_frames: int | None
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, object] | None = None
    diagnostic_report: str | None = None

    def to_dict(self) -> dict[str, object]:
        error: dict[str, object] | None = None
        if self.error_code is not None:
            error = {"code": self.error_code, "message": self.error_message}
            if self.error_details is not None:
                error["details"] = self.error_details
            if self.diagnostic_report is not None:
                error["diagnosticReport"] = self.diagnostic_report
        return {
            "productId": self.product_id,
            "status": self.status,
            "attempts": self.attempts,
            "removedFrames": self.removed_frames,
            "publishedFrames": self.published_frames,
            "error": error,
        }


@dataclass(frozen=True, slots=True)
class CycleResult:
    generated_at: datetime
    products: tuple[ProductCycleResult, ...]

    @property
    def successful(self) -> bool:
        return all(product.error_code is None for product in self.products)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.successful else "partial-error",
            "generatedAt": isoformat_utc(self.generated_at),
            "products": [product.to_dict() for product in self.products],
        }


class HistoryWorker:
    def __init__(
        self,
        service: IngestionService,
        *,
        data_dir: Path,
        products: tuple[RadarProduct, ...],
        retry_policy: RetryPolicy,
        retention_hours: float = 24.0,
        history_hours: float = 3.0,
        timeline_processor: RegionalTimelineProcessor | None = None,
        product_delay_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if product_delay_seconds < 0:
            raise ValueError("product_delay_seconds debe ser cero o mayor.")
        self.service = service
        self.products = products
        self.retry_policy = retry_policy
        self.sleeper = sleeper
        self.data_dir = data_dir.resolve()
        self.timeline_processor = timeline_processor
        self.product_delay_seconds = product_delay_seconds
        self.manifests = ManifestPublisher(
            data_dir,
            history_hours=history_hours,
            image_resolver=(
                timeline_processor.frame_image if timeline_processor is not None else None
            ),
            radar_metadata_resolver=(
                timeline_processor.radar_metadata if timeline_processor is not None else None
            ),
        )
        self.retention = RetentionManager(data_dir, retention_hours=retention_hours)
        self.health = HealthPublisher(data_dir, self.manifests)
        self.failures = FailureRecorder(data_dir)

    def run_cycle(self, *, generated_at: datetime | None = None) -> CycleResult:
        cycle_time = generated_at or datetime.now(UTC)
        results: list[ProductCycleResult] = []
        observations: dict[str, PollObservation] = {}

        for product in self.products:
            if not self.manifests.manifest_path(product).is_file():
                self.manifests.rebuild_product(product, generated_at=cycle_time)

        for product_index, product in enumerate(self.products):
            attempt_count = 0

            def fetch() -> FetchOutcome:
                nonlocal attempt_count
                attempt_count += 1
                return self.service.fetch_once(product)

            try:
                outcome, _ = call_with_retry(
                    fetch,
                    self.retry_policy,
                    sleeper=self.sleeper,
                )
            except AemetRadarError as exc:
                if is_no_data_error(exc):
                    try:
                        removed_frames, published_frames = self._refresh_publication(
                            product,
                            cycle_time=cycle_time,
                        )
                    except (AemetRadarError, OSError, ValueError):
                        message = "No se pudo actualizar de forma segura el archivo público."
                        observations[product.id] = PollObservation(
                            status="error",
                            checked_at=cycle_time,
                            attempts=attempt_count,
                            error_code="publication_error",
                            error_message=message,
                        )
                        results.append(
                            ProductCycleResult(
                                product_id=product.id,
                                status="error",
                                attempts=attempt_count,
                                removed_frames=0,
                                published_frames=None,
                                error_code="publication_error",
                                error_message=message,
                            )
                        )
                    else:
                        observations[product.id] = PollObservation(
                            status="no-data",
                            checked_at=cycle_time,
                            attempts=attempt_count,
                            outcome_status="no-data",
                        )
                        results.append(
                            ProductCycleResult(
                                product_id=product.id,
                                status="no-data",
                                attempts=attempt_count,
                                removed_frames=removed_frames,
                                published_frames=published_frames,
                            )
                        )
                    self._pause_between_products(product_index)
                    continue
                error_details = exc.safe_details() or None
                diagnostic_report: str | None = None
                if isinstance(exc, DownloadValidationError):
                    try:
                        diagnostic_path = self.failures.record_download_validation(
                            product=product,
                            checked_at=cycle_time,
                            attempts=attempt_count,
                            error=exc,
                        )
                    except OSError:
                        diagnostic_path = None
                    if diagnostic_path is not None:
                        diagnostic_report = diagnostic_path.relative_to(self.data_dir).as_posix()
                observations[product.id] = PollObservation(
                    status="error",
                    checked_at=cycle_time,
                    attempts=attempt_count,
                    error_code=exc.code,
                    error_message=str(exc),
                    error_details=error_details,
                    diagnostic_report=diagnostic_report,
                )
                results.append(
                    ProductCycleResult(
                        product_id=product.id,
                        status="error",
                        attempts=attempt_count,
                        removed_frames=0,
                        published_frames=None,
                        error_code=exc.code,
                        error_message=str(exc),
                        error_details=error_details,
                        diagnostic_report=diagnostic_report,
                    )
                )
                self._pause_between_products(product_index)
                continue

            try:
                removed_frames, published_frames = self._refresh_publication(
                    product,
                    cycle_time=cycle_time,
                )
            except (AemetRadarError, OSError, ValueError):
                message = "No se pudo actualizar de forma segura el archivo público."
                observations[product.id] = PollObservation(
                    status="error",
                    checked_at=cycle_time,
                    attempts=attempt_count,
                    error_code="publication_error",
                    error_message=message,
                )
                results.append(
                    ProductCycleResult(
                        product_id=product.id,
                        status="error",
                        attempts=attempt_count,
                        removed_frames=0,
                        published_frames=None,
                        error_code="publication_error",
                        error_message=message,
                    )
                )
                self._pause_between_products(product_index)
                continue

            observations[product.id] = PollObservation(
                status="success",
                checked_at=cycle_time,
                attempts=attempt_count,
                outcome_status=outcome.status,
            )
            results.append(
                ProductCycleResult(
                    product_id=product.id,
                    status=outcome.status,
                    attempts=attempt_count,
                    removed_frames=removed_frames,
                    published_frames=published_frames,
                )
            )
            self._pause_between_products(product_index)

        self.manifests.rebuild_index(self.products, generated_at=cycle_time)
        self.health.publish(
            self.products,
            generated_at=cycle_time,
            polls=observations,
        )
        return CycleResult(generated_at=cycle_time, products=tuple(results))

    def _refresh_publication(
        self,
        product: RadarProduct,
        *,
        cycle_time: datetime,
    ) -> tuple[int, int]:
        retention = self.retention.prune_product(
            product,
            reference_time=cycle_time,
        )
        if self.timeline_processor is not None:
            scan = scan_product_history(self.data_dir, product)
            self.timeline_processor.ensure_frames(
                product,
                select_history_frames(scan.frames, self.manifests.history_hours),
            )
        manifest = self.manifests.rebuild_product(
            product,
            generated_at=cycle_time,
        )
        frames = manifest.payload.get("frames")
        published_frames = len(frames) if isinstance(frames, list) else 0
        return retention.removed_frames, published_frames

    def _pause_between_products(self, product_index: int) -> None:
        if product_index < len(self.products) - 1 and self.product_delay_seconds > 0:
            self.sleeper(self.product_delay_seconds)


def run_periodically(
    callback: Callable[[], object],
    *,
    interval_seconds: float,
    max_cycles: int | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Ejecuta ciclos sin acumular el tiempo consumido por cada consulta."""

    if interval_seconds <= 0:
        raise ValueError("interval_seconds debe ser mayor que cero.")
    if max_cycles is not None and max_cycles <= 0:
        raise ValueError("max_cycles debe ser mayor que cero.")

    completed = 0
    next_start = monotonic()
    while max_cycles is None or completed < max_cycles:
        callback()
        completed += 1
        if max_cycles is not None and completed >= max_cycles:
            break
        next_start += interval_seconds
        sleeper(max(0.0, next_start - monotonic()))
    return completed
