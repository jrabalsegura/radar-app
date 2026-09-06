import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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


def test_derivative_gc_protects_live_shared_hashes_and_waits_after_last_reference(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    _archive_report(tmp_path, index=1, retrieved_at=now)
    live = tmp_path / "radar" / MURCIA.id / "frames" / f"{1:064x}" / "old-version"
    orphan = tmp_path / "radar" / MURCIA.id / "frames" / f"{2:064x}"
    processed = tmp_path / "processed" / MURCIA.id / f"{2:064x}"
    for directory in (live, orphan, processed):
        directory.mkdir(parents=True)
        image = directory / "overlay.png"
        image.write_bytes(b"image")
        for path in (image, directory):
            os.utime(path, (now.timestamp() - 72 * 3600,) * 2)
    manager = RetentionManager(tmp_path)
    assert manager.prune_product(MURCIA, reference_time=now).removed_derivatives == 0
    assert (
        manager.prune_product(MURCIA, reference_time=now + timedelta(hours=23)).removed_derivatives
        == 0
    )
    result = manager.prune_product(MURCIA, reference_time=now + timedelta(hours=25))
    assert result.removed_derivatives == 2
    assert result.reclaimed_bytes == 10
    assert live.is_dir() and not orphan.exists() and not processed.exists()


def test_unreadable_manifest_stops_cleanup(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    raw, report = _archive_report(tmp_path, index=1, retrieved_at=now - timedelta(days=3))
    _archive_report(tmp_path, index=2, retrieved_at=now)
    manifest = tmp_path / "radar" / MURCIA.id / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{broken")
    with pytest.raises(ValueError):
        RetentionManager(tmp_path).prune_product(MURCIA, reference_time=now)
    assert raw.exists() and report.exists()


def test_expired_observation_cannot_delete_raw_shared_with_another_time(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    raw, old_report = _archive_report(tmp_path, index=1, retrieved_at=now - timedelta(hours=30))
    payload = json.loads(old_report.read_text())
    payload["retrievedAt"] = _isoformat(now)
    second_report = old_report.with_name("second-observation.json")
    payload["files"]["report"] = second_report.relative_to(tmp_path).as_posix()
    second_report.write_text(json.dumps(payload))
    result = RetentionManager(tmp_path).prune_product(MURCIA, reference_time=now)
    assert result.removed_frames == 1
    assert raw.is_file() and second_report.is_file()
    assert not old_report.exists()
