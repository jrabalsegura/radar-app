from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image

from aemet_radar.history import scan_product_history
from aemet_radar.models import BatchFetchOutcome
from aemet_radar.national_client import (
    NationalFrame,
    NationalImage,
    NationalTimeline,
)
from aemet_radar.national_service import NationalIngestionService
from aemet_radar.products import NATIONAL
from aemet_radar.storage import ArchiveStore
from aemet_radar.viewer_client import MapCoordinates

COORDINATES = (
    (-16.08, 51.3),
    (12.14, 51.3),
    (12.14, 27.22),
    (-16.08, 27.22),
)


def test_archives_24_real_national_observations_and_is_idempotent(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 7, 27, 7, 10, tzinfo=UTC)
    frames = tuple(
        NationalFrame(
            observed_at=start + timedelta(minutes=10 * index),
            file_name=(
                f"radw{(start + timedelta(minutes=10 * index)).strftime('%Y%m%d%H%M')}_3857.png"
            ),
            product="Composicion radar",
        )
        for index in range(24)
    )
    viewer = NationalViewerStub(
        NationalTimeline(frames, tuple(frame.observed_at for frame in frames))
    )
    service = NationalIngestionService(
        viewer,  # type: ignore[arg-type]
        FallbackMustNotRun(),  # type: ignore[arg-type]
        ArchiveStore(tmp_path),
    )

    first = service.fetch_once(NATIONAL)
    service.begin_cycle()
    second = service.fetch_once(NATIONAL)

    assert isinstance(first, BatchFetchOutcome)
    assert isinstance(second, BatchFetchOutcome)
    assert first.status == "stored"
    assert first.stored_frames == 24
    assert second.status == "duplicate"
    assert second.duplicate_frames == 24
    scan = scan_product_history(tmp_path, NATIONAL)
    assert len(scan.frames) == 24
    assert [frame.source_id for frame in scan.frames] == [frame.file_name for frame in frames]


class NationalViewerStub:
    def __init__(self, timeline: NationalTimeline) -> None:
        self.timeline = timeline
        self.content = _national_png()

    def fetch_timeline(self) -> NationalTimeline:
        return self.timeline

    def fetch_image(self, frame: NationalFrame) -> NationalImage:
        return NationalImage(
            frame=frame,
            content=self.content,
            retrieved_at=frame.observed_at + timedelta(minutes=2),
            headers={"content-type": "image/png"},
        )

    def fetch_bounds(self, _frame: NationalFrame) -> MapCoordinates:
        return COORDINATES


class FallbackMustNotRun:
    def fetch_once(self, _product: object) -> None:
        raise AssertionError("OpenData no debe ejecutarse con el visor válido")


def _national_png() -> bytes:
    image = Image.new("P", (962, 1079), 0)
    palette = [
        255,
        255,
        255,
        239,
        242,
        249,
        0,
        0,
        252,
    ] + [0] * (256 * 3 - 9)
    image.putpalette(palette)
    image.putpixel((10, 10), 2)
    buffer = BytesIO()
    image.save(
        buffer,
        format="PNG",
        bits=4,
        transparency=bytes([0, 178, 178]),
    )
    return buffer.getvalue()
