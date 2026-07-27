import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aemet_radar.manifests import ManifestPublisher
from aemet_radar.products import MURCIA, NATIONAL, RadarProduct


def test_manifest_orders_twenty_four_frames_and_publishes_three_hours_fifty(
    tmp_path: Path,
) -> None:
    latest = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    times = [latest - timedelta(minutes=10 * index) for index in range(23, -1, -1)]
    for index, product_time in reversed(list(enumerate(times, start=1))):
        _archive_report(tmp_path, index=index, product_time=product_time)
    _archive_report(tmp_path, index=99, product_time=latest - timedelta(hours=4))

    result = ManifestPublisher(tmp_path).rebuild_product(
        MURCIA,
        generated_at=latest + timedelta(minutes=1),
    )

    frames = result.payload["frames"]
    assert isinstance(frames, list)
    assert len(frames) == 24
    assert [frame["time"] for frame in frames] == [
        _isoformat(product_time) for product_time in times
    ]
    assert result.payload["latestFrameTime"] == "2026-07-24T12:00:00Z"
    assert result.payload["window"] == {
        "hours": 23 / 6,
        "minutes": 230,
        "start": "2026-07-24T08:10:00Z",
        "end": "2026-07-24T12:00:00Z",
        "anchor": "latest-available-frame",
    }
    assert result.payload["timeBasis"] == "productTime"
    assert result.payload["gaps"] == []
    assert result.payload["statistics"] == {
        "archivedFrames": 25,
        "publishedFrames": 24,
        "discardedDuplicates": 0,
        "invalidReports": 0,
    }
    assert len(list((tmp_path / "raw").rglob("*.gif"))) == 25
    assert all(frame["imageUrl"] is None for frame in frames)
    assert all(frame["imageCoordinates"] is None for frame in frames)


def test_manifest_deduplicates_and_resolves_same_time_by_latest_retrieval(
    tmp_path: Path,
) -> None:
    product_time = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    first_hash = _archive_report(
        tmp_path,
        index=1,
        product_time=product_time,
        retrieved_at=product_time + timedelta(minutes=1),
    )
    _archive_report(
        tmp_path,
        index=1,
        product_time=product_time,
        retrieved_at=product_time + timedelta(minutes=2),
        bucket=("2026", "07", "25"),
    )
    replacement_hash = _archive_report(
        tmp_path,
        index=2,
        product_time=product_time,
        retrieved_at=product_time + timedelta(minutes=3),
    )

    result = ManifestPublisher(tmp_path).rebuild_product(
        MURCIA,
        generated_at=product_time + timedelta(minutes=4),
    )

    frames = result.payload["frames"]
    assert isinstance(frames, list)
    assert len(frames) == 1
    assert frames[0]["sourceHash"] == f"sha256:{replacement_hash}"
    assert frames[0]["sourceHash"] != f"sha256:{first_hash}"
    statistics = result.payload["statistics"]
    assert isinstance(statistics, dict)
    assert statistics["discardedDuplicates"] == 2


def test_manifest_represents_gap_and_late_data_fills_it(tmp_path: Path) -> None:
    start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    expected = [start + timedelta(minutes=10 * index) for index in range(13)]
    missing_time = expected[6]
    for index, product_time in enumerate(expected, start=1):
        if product_time != missing_time:
            _archive_report(tmp_path, index=index, product_time=product_time)

    publisher = ManifestPublisher(tmp_path)
    incomplete = publisher.rebuild_product(
        MURCIA,
        generated_at=expected[-1] + timedelta(minutes=1),
    )

    incomplete_frames = incomplete.payload["frames"]
    assert isinstance(incomplete_frames, list)
    assert len(incomplete_frames) == 12
    gaps = incomplete.payload["gaps"]
    assert gaps == [
        {
            "after": "2026-07-24T10:50:00Z",
            "before": "2026-07-24T11:10:00Z",
            "expectedCadenceMinutes": 10,
            "missingCount": 1,
            "expectedTimes": ["2026-07-24T11:00:00Z"],
            "timeBasis": "productTime",
        }
    ]

    _archive_report(
        tmp_path,
        index=50,
        product_time=missing_time,
        retrieved_at=expected[-1] + timedelta(minutes=5),
    )
    complete = publisher.rebuild_product(
        MURCIA,
        generated_at=expected[-1] + timedelta(minutes=6),
    )

    complete_frames = complete.payload["frames"]
    assert isinstance(complete_frames, list)
    assert len(complete_frames) == 13
    assert complete.payload["gaps"] == []
    assert [frame["time"] for frame in complete_frames] == [
        _isoformat(product_time) for product_time in expected
    ]


def test_manifest_represents_leading_missing_viewer_observations(
    tmp_path: Path,
) -> None:
    latest = datetime(2026, 7, 27, 8, 10, tzinfo=UTC)
    times = [latest - timedelta(minutes=20), latest - timedelta(minutes=10), latest]
    for index, product_time in enumerate(times, start=1):
        _archive_report(
            tmp_path,
            index=index,
            product_time=product_time,
            source_provider="aemet-viewer",
        )

    result = ManifestPublisher(tmp_path).rebuild_product(
        MURCIA,
        generated_at=latest + timedelta(minutes=1),
    )

    gaps = result.payload["gaps"]
    assert isinstance(gaps, list)
    assert gaps == [
        {
            "after": None,
            "before": "2026-07-27T07:50:00Z",
            "expectedCadenceMinutes": 10,
            "missingCount": 21,
            "expectedTimes": [
                _isoformat(latest - timedelta(minutes=230) + timedelta(minutes=10 * index))
                for index in range(21)
            ],
            "timeBasis": "productTime",
        }
    ]


def test_manifest_marks_retrieval_time_fallback_and_invalid_reports(
    tmp_path: Path,
) -> None:
    retrieved_at = datetime(2026, 7, 24, 12, 3, tzinfo=UTC)
    _archive_report(tmp_path, index=1, product_time=None, retrieved_at=retrieved_at)
    invalid = tmp_path / "raw" / MURCIA.id / "2026" / "07" / "24" / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")

    result = ManifestPublisher(tmp_path).rebuild_product(
        MURCIA,
        generated_at=retrieved_at + timedelta(minutes=1),
    )

    frames = result.payload["frames"]
    assert isinstance(frames, list)
    assert frames[0]["time"] == "2026-07-24T12:03:00Z"
    assert frames[0]["timeSource"] == "retrievedAt"
    assert frames[0]["productTime"] is None
    assert result.payload["timeBasis"] == "retrievedAt"
    statistics = result.payload["statistics"]
    assert isinstance(statistics, dict)
    assert statistics["invalidReports"] == 1


def test_gap_detection_tolerates_real_polling_jitter(tmp_path: Path) -> None:
    before = datetime(2026, 7, 24, 18, 27, 31, 850929, tzinfo=UTC)
    after = datetime(2026, 7, 24, 18, 42, 31, 813742, tzinfo=UTC)
    _archive_report(
        tmp_path,
        index=1,
        product_time=None,
        retrieved_at=before,
    )
    _archive_report(
        tmp_path,
        index=2,
        product_time=None,
        retrieved_at=after,
    )

    result = ManifestPublisher(tmp_path).rebuild_product(
        MURCIA,
        generated_at=after + timedelta(minutes=1),
    )

    assert result.payload["gaps"] == [
        {
            "after": "2026-07-24T18:27:31.850929Z",
            "before": "2026-07-24T18:42:31.813742Z",
            "expectedCadenceMinutes": 10,
            "missingCount": 1,
            "expectedTimes": ["2026-07-24T18:37:31.850929Z"],
            "timeBasis": "retrievedAt",
        }
    ]


def test_national_manifest_uses_its_verified_ten_minute_cadence(
    tmp_path: Path,
) -> None:
    start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    times = [start + timedelta(minutes=10 * index) for index in range(5)]
    for index, product_time in enumerate(times, start=1):
        _archive_report(
            tmp_path,
            index=index,
            product_time=product_time,
            product=NATIONAL,
        )

    result = ManifestPublisher(tmp_path).rebuild_product(
        NATIONAL,
        generated_at=times[-1] + timedelta(minutes=1),
    )

    frames = result.payload["frames"]
    assert isinstance(frames, list)
    assert len(frames) == 5
    assert result.payload["radar"] == {
        "id": "national",
        "label": "Composición nacional",
        "kind": "national",
        "cadenceMinutes": 10,
    }
    assert result.payload["gaps"] == []


def _archive_report(
    data_dir: Path,
    *,
    index: int,
    product_time: datetime | None,
    retrieved_at: datetime | None = None,
    bucket: tuple[str, str, str] = ("2026", "07", "24"),
    product: RadarProduct = MURCIA,
    source_provider: str | None = None,
) -> str:
    retrieval = retrieved_at or product_time
    if retrieval is None:
        raise ValueError("retrieved_at es obligatorio sin product_time")
    digest = f"{index:064x}"
    directory = data_dir / "raw" / product.id
    for part in bucket:
        directory /= part
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / f"{digest}{'.png' if source_provider else '.gif'}"
    report_path = directory / f"{digest}.json"
    raw_path.write_bytes(b"GIF89a synthetic")
    raw_relative = raw_path.relative_to(data_dir).as_posix()
    report = {
        "schemaVersion": 1,
        "product": {
            "id": product.id,
            "label": product.label,
            "kind": product.kind.value,
            "cadenceMinutes": product.cadence_minutes,
        },
        "retrievedAt": _isoformat(retrieval),
        "image": {"sha256": digest},
        "productTime": {
            "status": "candidate" if product_time is not None else "unresolved",
            "value": _isoformat(product_time) if product_time is not None else None,
        },
        "files": {
            "raw": raw_relative,
            "report": report_path.relative_to(data_dir).as_posix(),
        },
    }
    if source_provider is not None:
        report["source"] = {
            "provider": source_provider,
            "observationId": f"fixture-{index}",
        }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return digest


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
