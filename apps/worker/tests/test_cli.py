import json
from pathlib import Path

import pytest

from aemet_radar.cli import main

REFLECTIVITY_FIXTURES = Path(__file__).parent / "fixtures" / "reflectivity"


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


def test_analyze_reflectivity_does_not_require_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("AEMET_API_KEY", raising=False)

    exit_code = main(
        [
            "analyze-reflectivity",
            str(REFLECTIVITY_FIXTURES / "source.gif"),
            "--config",
            str(REFLECTIVITY_FIXTURES / "config.json"),
            "--mask",
            str(REFLECTIVITY_FIXTURES / "static-mask.png"),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capfd.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["processor"] == "regional-v1"
    assert payload["reflectivityPixels"] == 15
    assert (tmp_path / "overlay.png").is_file()
    assert (tmp_path / "report.json").is_file()
