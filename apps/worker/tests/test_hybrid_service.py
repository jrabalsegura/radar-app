from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image

from aemet_radar.history import scan_product_history
from aemet_radar.hybrid_service import HybridIngestionService
from aemet_radar.models import BatchFetchOutcome
from aemet_radar.products import MURCIA
from aemet_radar.radar_catalog import load_radar_catalog
from aemet_radar.storage import ArchiveStore
from aemet_radar.viewer_client import ViewerFrame, ViewerImage, ViewerTimeline

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RADAR_CATALOG = REPOSITORY_ROOT / "config" / "radars.yaml"
COORDINATES = ((-7.0, 42.0), (4.0, 42.0), (4.0, 34.0), (-7.0, 34.0))


def test_archives_all_twenty_four_real_observations_and_is_idempotent(
    tmp_path: Path,
) -> None:
    frames = _frames(24)
    viewer = ViewerStub(ViewerTimeline(frames))
    fallback = FallbackStub()
    service = HybridIngestionService(
        viewer,  # type: ignore[arg-type]
        fallback,  # type: ignore[arg-type]
        ArchiveStore(tmp_path),
        catalog=load_radar_catalog(RADAR_CATALOG),
    )

    first = service.fetch_once(MURCIA)
    service.begin_cycle()
    second = service.fetch_once(MURCIA)

    assert isinstance(first, BatchFetchOutcome)
    assert isinstance(second, BatchFetchOutcome)
    assert first.status == "stored"
    assert first.stored_frames == 24
    assert second.status == "duplicate"
    assert second.stored_frames == 0
    assert fallback.calls == 0
    assert len(list((tmp_path / "raw").rglob("*.png"))) == 24
    scan = scan_product_history(tmp_path, MURCIA)
    assert len(scan.frames) == 24
    assert len({frame.source_id for frame in scan.frames}) == 24
    # El contenido puede ser idéntico sin convertir observaciones distintas en duplicados.
    assert len({frame.source_hash for frame in scan.frames}) == 1
    assert [frame.timeline_time for frame in scan.frames] == [frame.observed_at for frame in frames]


def test_keeps_valid_older_ppi_and_still_calls_fallback_for_missing_latest(
    tmp_path: Path,
) -> None:
    frames = _frames(2)
    sentinel = object()
    viewer = ViewerStub(ViewerTimeline(frames), unavailable_latest=True)
    fallback = FallbackStub(result=sentinel)
    service = HybridIngestionService(
        viewer,  # type: ignore[arg-type]
        fallback,  # type: ignore[arg-type]
        ArchiveStore(tmp_path),
        catalog=load_radar_catalog(RADAR_CATALOG),
    )

    result = service.fetch_once(MURCIA)

    assert result is not sentinel
    assert isinstance(result, BatchFetchOutcome)
    assert result.status == "stored"
    assert result.stored_frames == 1
    assert result.skipped_frames == 1
    assert fallback.calls == 1
    assert len(list((tmp_path / "raw").rglob("*.png"))) == 1


def test_returns_opendata_result_when_no_viewer_frame_is_usable(
    tmp_path: Path,
) -> None:
    sentinel = object()
    viewer = ViewerStub(ViewerTimeline(_frames(2)), unavailable_all=True)
    fallback = FallbackStub(result=sentinel)
    service = HybridIngestionService(
        viewer,  # type: ignore[arg-type]
        fallback,  # type: ignore[arg-type]
        ArchiveStore(tmp_path),
        catalog=load_radar_catalog(RADAR_CATALOG),
    )

    result = service.fetch_once(MURCIA)

    assert result is sentinel
    assert fallback.calls == 1
    assert not (tmp_path / "raw").exists()


class ViewerStub:
    def __init__(
        self,
        timeline: ViewerTimeline,
        *,
        unavailable_latest: bool = False,
        unavailable_all: bool = False,
    ) -> None:
        self.timeline = timeline
        self.unavailable_latest = unavailable_latest
        self.unavailable_all = unavailable_all
        self.timeline_calls = 0

    def fetch_timeline(self) -> ViewerTimeline:
        self.timeline_calls += 1
        return self.timeline

    def fetch_image(self, frame: ViewerFrame) -> ViewerImage:
        unavailable = self.unavailable_all or (
            self.unavailable_latest and frame.file_name == self.timeline.frames[-1].file_name
        )
        return ViewerImage(
            frame=frame,
            content=_png(unavailable=unavailable),
            retrieved_at=frame.observed_at + timedelta(minutes=1),
            headers={"content-type": "image/png"},
        )

    def fetch_bounds(self, _frame: ViewerFrame) -> object:
        return COORDINATES


class FallbackStub:
    def __init__(self, result: object | None = None) -> None:
        self.result = result
        self.calls = 0

    def fetch_once(self, _product: object) -> object:
        self.calls += 1
        return self.result


def _frames(count: int) -> tuple[ViewerFrame, ...]:
    start = datetime(2026, 7, 27, 6, 0, tzinfo=UTC)
    return tuple(
        ViewerFrame(
            site_code="FTN",
            radar_name="Murcia - Fortuna",
            observed_at=start + timedelta(minutes=10 * index),
            file_name=(
                f"FTN{(start + timedelta(minutes=10 * index)).strftime('%y%m%d%H%M%S')}"
                ".PPI.Z_005_240.png"
            ),
            product="PPI",
            subproduct="Z_005_240",
        )
        for index in range(count)
    )


def _png(*, unavailable: bool) -> bytes:
    image = Image.new("RGBA", (1000, 1000), (239, 242, 249, 179))
    image.putpixel((999, 999), (0, 0, 0, 0))
    if unavailable:
        image.putpixel((2, 2), (1, 1, 1, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
