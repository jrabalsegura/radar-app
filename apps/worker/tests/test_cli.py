import json
from pathlib import Path

import pytest

from aemet_radar.cli import main

REFLECTIVITY_FIXTURES = Path(__file__).parent / "fixtures" / "reflectivity"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GEOREFERENCING_CONFIG = REPOSITORY_ROOT / "config" / "georeferencing" / "regional-mu-v1.json"


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


def test_georeference_murcia_does_not_require_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    from PIL import Image

    monkeypatch.delenv("AEMET_API_KEY", raising=False)
    source_path = tmp_path / "overlay.png"
    Image.new("RGBA", (480, 480), (0, 0, 0, 0)).save(source_path)

    exit_code = main(
        [
            "georeference-murcia",
            str(source_path),
            "--config",
            str(GEOREFERENCING_CONFIG),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capfd.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["processor"] == "regional-georeference-v1"
    assert payload["meanErrorKilometres"] == pytest.approx(0.368942)
    assert payload["maximumErrorKilometres"] == pytest.approx(0.699806)
    assert (tmp_path / "output" / "overlay-3857.png").is_file()
    assert (tmp_path / "output" / "georeferencing.json").is_file()
