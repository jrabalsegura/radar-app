from pathlib import Path

import pytest

from aemet_radar.cli import main


def test_rebuild_manifests_does_not_require_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AEMET_API_KEY", raising=False)

    exit_code = main(
        [
            "rebuild-manifests",
            "--data-dir",
            str(tmp_path),
            "--product",
            "regional-mu",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "radar" / "regional-mu" / "manifest.json").is_file()
    assert (tmp_path / "radar" / "index.json").is_file()
    assert (tmp_path / "status" / "health.json").is_file()
