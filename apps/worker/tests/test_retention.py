import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aemet_radar.products import MURCIA
from aemet_radar.retention import RetentionManager


def test_retention_removes_pairs_older_than_24_hours(tmp_path: Path) -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    old_paths = [
        _archive_report(tmp_path, index=1, retrieved_at=now - timedelta(hours=26)),
        _archive_report(tmp_path, index=2, retrieved_at=now - timedelta(hours=25)),
    ]
    recent_paths = _archive_report(
        tmp_path,
        index=3,
        retrieved_at=now - timedelta(hours=1),
    )

    result = RetentionManager(tmp_path).prune_product(MURCIA, reference_time=now)

    assert result.removed_frames == 2
    assert result.retained_frames == 1
    for raw_path, report_path in old_paths:
        assert not raw_path.exists()
        assert not report_path.exists()
    assert recent_paths[0].exists()
    assert recent_paths[1].exists()


def test_retention_never_removes_only_latest_valid_frame(tmp_path: Path) -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    paths = _archive_report(
        tmp_path,
        index=1,
        retrieved_at=now - timedelta(days=3),
    )

    result = RetentionManager(tmp_path).prune_product(MURCIA, reference_time=now)

    assert result.removed_frames == 0
    assert result.retained_frames == 1
    assert paths[0].exists()
    assert paths[1].exists()


def test_duplicate_seen_recently_is_retained(tmp_path: Path) -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    old_recently_seen = _archive_report(
        tmp_path,
        index=1,
        retrieved_at=now - timedelta(hours=30),
        last_retrieved_at=now - timedelta(minutes=5),
    )
    latest = _archive_report(
        tmp_path,
        index=2,
        retrieved_at=now - timedelta(hours=1),
    )

    result = RetentionManager(tmp_path).prune_product(MURCIA, reference_time=now)

    assert result.removed_frames == 0
    assert old_recently_seen[0].exists()
    assert latest[0].exists()


def _archive_report(
    data_dir: Path,
    *,
    index: int,
    retrieved_at: datetime,
    last_retrieved_at: datetime | None = None,
) -> tuple[Path, Path]:
    digest = f"{index:064x}"
    directory = data_dir / "raw" / MURCIA.id / "2026" / "07" / "24"
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = directory / f"{digest}.gif"
    report_path = directory / f"{digest}.json"
    raw_path.write_bytes(b"GIF89a synthetic")
    report = {
        "product": {"id": MURCIA.id},
        "retrievedAt": _isoformat(retrieved_at),
        "lastRetrievedAt": (
            _isoformat(last_retrieved_at) if last_retrieved_at is not None else None
        ),
        "image": {"sha256": digest},
        "productTime": {"status": "unresolved", "value": None},
        "files": {
            "raw": raw_path.relative_to(data_dir).as_posix(),
            "report": report_path.relative_to(data_dir).as_posix(),
        },
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return raw_path, report_path


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
