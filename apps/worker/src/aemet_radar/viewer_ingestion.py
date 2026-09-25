"""Algoritmo común para archivar la cronología del visor con OpenData como respaldo."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal, Protocol

from aemet_radar.common import MapCoordinates, stored_viewer_coordinates
from aemet_radar.errors import AemetRadarError
from aemet_radar.history import isoformat_utc, scan_product_history
from aemet_radar.models import BatchFetchOutcome, FetchOutcome
from aemet_radar.products import RadarProduct
from aemet_radar.service import IngestionService
from aemet_radar.storage import ArchiveStore

IngestionOutcome = FetchOutcome | BatchFetchOutcome
ViewerSource = Literal["aemet-viewer", "aemet-viewer-national"]


class ViewerFrameLike(Protocol):
    @property
    def file_name(self) -> str: ...

    @property
    def observed_at(self) -> datetime: ...


class ViewerImageLike(Protocol):
    @property
    def content(self) -> bytes: ...

    @property
    def retrieved_at(self) -> datetime: ...

    @property
    def headers(self) -> dict[str, str]: ...


class InspectionLike(Protocol):
    @property
    def sha256(self) -> str: ...

    def to_dict(self) -> dict[str, object]: ...


class ViewerTimelineIngestion[TimelineT, FrameT: ViewerFrameLike, ImageT: ViewerImageLike](ABC):
    """Archiva las observaciones visibles del visor y aplica fallback si falta la última."""

    source: ViewerSource

    def __init__(self, fallback: IngestionService, store: ArchiveStore) -> None:
        self._fallback = fallback
        self._store = store
        self._timeline: TimelineT | None = None
        self._timeline_error: AemetRadarError | None = None

    @abstractmethod
    def _fetch_timeline(self) -> TimelineT: ...

    @abstractmethod
    def _frames_for(self, timeline: TimelineT, product: RadarProduct) -> tuple[FrameT, ...]:
        """Observaciones del producto; ``KeyError`` equivale a no tener cronología."""

    @abstractmethod
    def _fetch_image(self, frame: FrameT) -> ImageT: ...

    @abstractmethod
    def _fetch_bounds(self, frame: FrameT) -> MapCoordinates: ...

    @abstractmethod
    def _inspect(self, image: ImageT) -> InspectionLike: ...

    @abstractmethod
    def _source_report(self, frame: FrameT) -> dict[str, object]: ...

    def begin_cycle(self) -> None:
        """Fuerza una sola lectura fresca de la cronología en cada ciclo."""

        self._timeline = None
        self._timeline_error = None

    def fetch_once(self, product: RadarProduct) -> IngestionOutcome:
        try:
            frames = self._frames_for(self._current_timeline(), product)
        except (AemetRadarError, KeyError):
            return self._fallback.fetch_once(product)
        if not frames:
            return self._fallback.fetch_once(product)

        archived = {
            frame.source_id: frame
            for frame in scan_product_history(self._store.data_dir, product).frames
        }
        latest = frames[-1]
        latest_is_archived = latest.file_name in archived
        coordinates: MapCoordinates | None = None
        stored = 0
        duplicates = sum(frame.file_name in archived for frame in frames)
        skipped = 0
        latest_failure: AemetRadarError | None = None
        latest_download: tuple[ImageT, InspectionLike] | None = None

        if latest_is_archived:
            coordinates = stored_viewer_coordinates(archived[latest.file_name].report_path)
        else:
            try:
                image = self._fetch_image(latest)
                latest_download = (image, self._inspect(image))
                coordinates = self._fetch_bounds(latest)
            except AemetRadarError as exc:
                latest_failure = exc

        if coordinates is None:
            try:
                coordinates = self._fetch_bounds(latest)
            except AemetRadarError:
                if latest_failure is not None:
                    return self._fallback.fetch_once(product)
                return BatchFetchOutcome(
                    product_id=product.id,
                    status="duplicate",
                    source=self.source,
                    stored_frames=0,
                    duplicate_frames=duplicates,
                    skipped_frames=len(frames) - duplicates,
                    latest_observation=latest.observed_at,
                )

        if latest_download is not None:
            latest_failure = None
            if self._archive(product, latest, *latest_download, coordinates) == "stored":
                stored += 1
            else:
                duplicates += 1
        elif not latest_is_archived:
            skipped += 1

        for frame in frames:
            if frame.file_name == latest.file_name or frame.file_name in archived:
                continue
            try:
                image = self._fetch_image(frame)
                status = self._archive(product, frame, image, self._inspect(image), coordinates)
            except AemetRadarError:
                skipped += 1
                continue
            if status == "stored":
                stored += 1
            else:
                duplicates += 1

        viewer_outcome = BatchFetchOutcome(
            product_id=product.id,
            status="stored" if stored else "duplicate",
            source=self.source,
            stored_frames=stored,
            duplicate_frames=duplicates,
            skipped_frames=skipped,
            latest_observation=latest.observed_at,
        )
        if latest_failure is None:
            return viewer_outcome
        try:
            fallback_outcome = self._fallback.fetch_once(product)
        except AemetRadarError:
            if stored:
                return viewer_outcome
            raise
        return viewer_outcome if stored else fallback_outcome

    def _current_timeline(self) -> TimelineT:
        if self._timeline is not None:
            return self._timeline
        if self._timeline_error is not None:
            raise self._timeline_error
        try:
            self._timeline = self._fetch_timeline()
        except AemetRadarError as exc:
            self._timeline_error = exc
            raise
        return self._timeline

    def _archive(
        self,
        product: RadarProduct,
        frame: FrameT,
        image: ImageT,
        inspection: InspectionLike,
        coordinates: MapCoordinates,
    ) -> str:
        observed_at = isoformat_utc(frame.observed_at)
        report: dict[str, object] = {
            "schemaVersion": 2,
            "product": {
                "id": product.id,
                "label": product.label,
                "kind": product.kind.value,
                "aemetCode": product.aemet_code,
                "endpoint": product.endpoint,
                "cadenceMinutes": product.cadence_minutes,
            },
            "source": self._source_report(frame),
            "retrievedAt": isoformat_utc(image.retrieved_at),
            "http": {"image": {"status": 200, "headers": image.headers}},
            "image": inspection.to_dict(),
            "productTime": {
                "status": "candidate",
                "value": observed_at,
                "source": f"{self.source}-filename",
                "confidence": "high",
                "evidence": [{"fileName": frame.file_name}],
                "notes": [],
            },
            "viewer": {
                "maplibreCoordinates": [list(coordinate) for coordinate in coordinates],
            },
        }
        result = self._store.archive(
            product=product,
            content=image.content,
            sha256=inspection.sha256,
            retrieved_at=image.retrieved_at,
            report=report,
            extension=".png",
            archive_key=frame.observed_at.strftime("%Y%m%dT%H%M%SZ") + "-" + inspection.sha256,
        )
        return result.status
