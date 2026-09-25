"""Ingesta nacional primaria desde el visor con OpenData como respaldo."""

from __future__ import annotations

from aemet_radar.common import MapCoordinates
from aemet_radar.hybrid_service import HybridIngestionService
from aemet_radar.national_client import (
    AemetNationalClient,
    NationalFrame,
    NationalImage,
    NationalTimeline,
)
from aemet_radar.national_processing import inspect_national_png
from aemet_radar.products import ProductKind, RadarProduct
from aemet_radar.service import IngestionService
from aemet_radar.storage import ArchiveStore
from aemet_radar.viewer_ingestion import (
    IngestionOutcome,
    InspectionLike,
    ViewerTimelineIngestion,
)


class NationalIngestionService(
    ViewerTimelineIngestion[NationalTimeline, NationalFrame, NationalImage]
):
    """Archiva las 24 observaciones nacionales visibles y aplica fallback."""

    source = "aemet-viewer-national"

    def __init__(
        self,
        viewer: AemetNationalClient,
        fallback: IngestionService,
        store: ArchiveStore,
    ) -> None:
        super().__init__(fallback, store)
        self._viewer = viewer

    def _fetch_timeline(self) -> NationalTimeline:
        return self._viewer.fetch_timeline()

    def _frames_for(
        self,
        timeline: NationalTimeline,
        product: RadarProduct,
    ) -> tuple[NationalFrame, ...]:
        return timeline.visible_frames()

    def _fetch_image(self, frame: NationalFrame) -> NationalImage:
        return self._viewer.fetch_image(frame)

    def _fetch_bounds(self, frame: NationalFrame) -> MapCoordinates:
        return self._viewer.fetch_bounds(frame)

    def _inspect(self, image: NationalImage) -> InspectionLike:
        return inspect_national_png(image.content, image.headers.get("content-type"))

    def _source_report(self, frame: NationalFrame) -> dict[str, object]:
        return {
            "provider": self.source,
            "observationId": frame.file_name,
            "regionCode": "PB",
            "fileName": frame.file_name,
            "product": frame.product,
        }


class RadarIngestionService:
    """Despacha regionales y nacional sin mezclar sus contratos."""

    def __init__(
        self,
        regional: HybridIngestionService,
        national: NationalIngestionService,
    ) -> None:
        self._regional = regional
        self._national = national

    def begin_cycle(self) -> None:
        self._regional.begin_cycle()
        self._national.begin_cycle()

    def fetch_once(self, product: RadarProduct) -> IngestionOutcome:
        if product.kind is ProductKind.NATIONAL:
            return self._national.fetch_once(product)
        return self._regional.fetch_once(product)
