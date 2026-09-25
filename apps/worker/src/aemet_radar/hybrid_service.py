"""Ingesta regional primaria desde el visor PPI con OpenData como respaldo."""

from __future__ import annotations

from aemet_radar.common import MapCoordinates
from aemet_radar.products import RadarProduct
from aemet_radar.radar_catalog import RadarCatalog
from aemet_radar.service import IngestionService
from aemet_radar.storage import ArchiveStore
from aemet_radar.viewer_client import (
    AemetViewerClient,
    ViewerFrame,
    ViewerImage,
    ViewerTimeline,
)
from aemet_radar.viewer_ingestion import (
    IngestionOutcome as IngestionOutcome,
)
from aemet_radar.viewer_ingestion import (
    InspectionLike,
    ViewerTimelineIngestion,
)
from aemet_radar.viewer_processing import inspect_viewer_png


class HybridIngestionService(ViewerTimelineIngestion[ViewerTimeline, ViewerFrame, ViewerImage]):
    """Prefiere las 24 observaciones PPI y delega en OpenData si falta la actual."""

    source = "aemet-viewer"

    def __init__(
        self,
        viewer: AemetViewerClient,
        fallback: IngestionService,
        store: ArchiveStore,
        *,
        catalog: RadarCatalog,
    ) -> None:
        super().__init__(fallback, store)
        self._viewer = viewer
        self._catalog = catalog

    def _fetch_timeline(self) -> ViewerTimeline:
        return self._viewer.fetch_timeline()

    def _frames_for(
        self,
        timeline: ViewerTimeline,
        product: RadarProduct,
    ) -> tuple[ViewerFrame, ...]:
        return timeline.frames_for(self._catalog.definition_for(product.id).site_code)

    def _fetch_image(self, frame: ViewerFrame) -> ViewerImage:
        return self._viewer.fetch_image(frame)

    def _fetch_bounds(self, frame: ViewerFrame) -> MapCoordinates:
        return self._viewer.fetch_bounds(frame)

    def _inspect(self, image: ViewerImage) -> InspectionLike:
        return inspect_viewer_png(image.content, image.headers.get("content-type"))

    def _source_report(self, frame: ViewerFrame) -> dict[str, object]:
        return {
            "provider": self.source,
            "observationId": frame.file_name,
            "siteCode": frame.site_code,
            "radarName": frame.radar_name,
            "fileName": frame.file_name,
            "product": frame.product,
            "subproduct": frame.subproduct,
        }
