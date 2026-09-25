from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aemet_radar.health import HealthPublisher
from aemet_radar.manifests import ManifestPublisher
from aemet_radar.products import NATIONAL


@pytest.mark.parametrize(
    ("age_minutes", "expected"),
    [
        # Latencia normal de AEMET (~18 min) más una cadencia y un sondeo.
        (33, "current"),
        (41, "delayed"),
    ],
)
def test_normal_aemet_latency_is_not_reported_as_delayed(
    tmp_path: Path,
    age_minutes: int,
    expected: str,
) -> None:
    now = datetime(2026, 9, 25, 18, 5, tzinfo=UTC)
    latest = (now - timedelta(minutes=age_minutes)).isoformat().replace("+00:00", "Z")
    manifest = tmp_path / "radar" / NATIONAL.id / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"latestFrameTime": latest, "frames": [{}]}))

    path = HealthPublisher(tmp_path, ManifestPublisher(tmp_path)).publish(
        (NATIONAL,),
        generated_at=now,
    )

    product = json.loads(path.read_text())["products"][0]
    assert product["dataStatus"] == expected
    assert product["staleAfterSeconds"] == 40 * 60
