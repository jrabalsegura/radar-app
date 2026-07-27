"""Ingesta primaria desde el visor PPI con OpenData como respaldo."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import cast

from aemet_radar.errors import AemetRadarError
from aemet_radar.history import scan_product_history
from aemet_radar.models import BatchFetchOutcome, FetchOutcome
from aemet_radar.products import RadarProduct
from aemet_radar.radar_catalog import RadarCatalog
from aemet_radar.service import IngestionService
from aemet_radar.storage import ArchiveStore
from aemet_radar.viewer_client import (
    AemetViewerClient,
    MapCoordinates,
    ViewerImage,
    ViewerTimeline,
)
from aemet_radar.viewer_processing import ViewerPpiInspection, inspect_viewer_png

IngestionOutcome = FetchOutcome | BatchFetchOutcome


class HybridIngestionService:
    """Prefiere las 24 observaciones PPI y delega en OpenData si falta la actual."""

    def __init__(
        self,
        viewer: AemetViewerClient,
        fallback: IngestionService,
        store: ArchiveStore,
        *,
        catalog: RadarCatalog,
    ) -> None:
        self._viewer = viewer
        self._fallback = fallback
        self._store = store
        self._catalog = catalog
        self._timeline: ViewerTimeline | None = None
        self._timeline_error: AemetRadarError | None = None

    def begin_cycle(self) -> None:
        """Fuerza una sola lectura fresca de la cronología en cada ciclo."""

        self._timeline = None
        self._timeline_error = None

    def fetch_once(self, product: RadarProduct) -> IngestionOutcome:
        try:
            timeline = self._current_timeline()
            site_code = self._catalog.definition_for(product.id).site_code
        except (AemetRadarError, KeyError):
            return self._fallback.fetch_once(product)

        frames = timeline.frames_for(site_code)
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
        latest_image: ViewerImage | None = None
        latest_inspection: ViewerPpiInspection | None = None

        if latest_is_archived:
            coordinates = _stored_coordinates(archived[latest.file_name].report_path)
        else:
            try:
                latest_image = self._viewer.fetch_image(latest)
                latest_inspection = inspect_viewer_png(
                    latest_image.content,
                    latest_image.headers.get("content-type"),
                )
                coordinates = self._viewer.fetch_bounds(latest)
            except AemetRadarError as exc:
                latest_failure = exc

        if coordinates is None:
            try:
                coordinates = self._viewer.fetch_bounds(latest)
            except AemetRadarError:
                if latest_failure is not None:
                    return self._fallback.fetch_once(product)
                return BatchFetchOutcome(
                    product_id=product.id,
                    status="duplicate",
                    source="aemet-viewer",
                    stored_frames=0,
                    duplicate_frames=duplicates,
                    skipped_frames=len(frames) - duplicates,
                    latest_observation=latest.observed_at,
                )

        if not latest_is_archived and latest_image is not None and latest_inspection is not None:
            status = self._archive_viewer_frame(
                product,
                latest_image,
                latest_inspection,
                coordinates,
            )
            latest_failure = None
            if status == "stored":
                stored += 1
            else:
                duplicates += 1
        elif not latest_is_archived:
            skipped += 1

        for frame in frames:
            if frame.file_name == latest.file_name or frame.file_name in archived:
                continue
            try:
                image = self._viewer.fetch_image(frame)
                inspection = inspect_viewer_png(
                    image.content,
                    image.headers.get("content-type"),
                )
                status = self._archive_viewer_frame(
                    product,
                    image,
                    inspection,
                    coordinates,
                )
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
            source="aemet-viewer",
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

    def _current_timeline(self) -> ViewerTimeline:
        if self._timeline is not None:
            return self._timeline
        if self._timeline_error is not None:
            raise self._timeline_error
        try:
            self._timeline = self._viewer.fetch_timeline()
        except AemetRadarError as exc:
            self._timeline_error = exc
            raise
        return self._timeline

    def _archive_viewer_frame(
        self,
        product: RadarProduct,
        image: ViewerImage,
        inspection: ViewerPpiInspection,
        coordinates: MapCoordinates,
    ) -> str:
        report = _build_viewer_report(
            product,
            image,
            inspection,
            coordinates,
        )
        archive_key = image.frame.observed_at.strftime("%Y%m%dT%H%M%SZ") + "-" + inspection.sha256
        result = self._store.archive(
            product=product,
            content=image.content,
            sha256=inspection.sha256,
            retrieved_at=image.retrieved_at,
            report=report,
            extension=".png",
            archive_key=archive_key,
        )
        return result.status


def _build_viewer_report(
    product: RadarProduct,
    image: ViewerImage,
    inspection: ViewerPpiInspection,
    coordinates: MapCoordinates,
) -> dict[str, object]:
    frame = image.frame
    return {
        "schemaVersion": 2,
        "product": {
            "id": product.id,
            "label": product.label,
            "kind": product.kind.value,
            "aemetCode": product.aemet_code,
            "endpoint": product.endpoint,
            "cadenceMinutes": product.cadence_minutes,
        },
        "source": {
            "provider": "aemet-viewer",
            "observationId": frame.file_name,
            "siteCode": frame.site_code,
            "radarName": frame.radar_name,
            "fileName": frame.file_name,
            "product": frame.product,
            "subproduct": frame.subproduct,
        },
        "retrievedAt": image.retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "http": {
            "image": {
                "status": 200,
                "headers": image.headers,
            }
        },
        "image": inspection.to_dict(),
        "productTime": {
            "status": "candidate",
            "value": frame.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "source": "aemet-viewer-filename",
            "confidence": "high",
            "evidence": [{"fileName": frame.file_name}],
            "notes": [],
        },
        "viewer": {
            "maplibreCoordinates": [list(coordinate) for coordinate in coordinates],
        },
    }


def _stored_coordinates(report_path: Path) -> MapCoordinates | None:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    viewer = payload.get("viewer")
    if not isinstance(viewer, dict):
        return None
    value = viewer.get("maplibreCoordinates")
    if not isinstance(value, list) or len(value) != 4:
        return None
    result: list[tuple[float, float]] = []
    for coordinate in value:
        if (
            not isinstance(coordinate, list)
            or len(coordinate) != 2
            or not all(
                isinstance(component, (int, float)) and not isinstance(component, bool)
                for component in coordinate
            )
        ):
            return None
        result.append((float(coordinate[0]), float(coordinate[1])))
    return cast(MapCoordinates, tuple(result))
