import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from aemet_radar.client import DEFAULT_BASE_URL, AemetClient
from aemet_radar.errors import DownloadValidationError
from aemet_radar.products import MURCIA
from aemet_radar.service import IngestionService
from aemet_radar.storage import ArchiveStore

FAKE_SECRET = "fixture-secret-that-must-never-leak"
DATA_URL = "https://opendata.aemet.es/opendata/sh/sanitized-data"
METADATA_URL = "https://opendata.aemet.es/opendata/sh/sanitized-metadata"


def test_archives_valid_gif_and_deduplicates_by_hash(
    tmp_path: Path,
    make_synthetic_gif: Callable[[bytes], bytes],
) -> None:
    gif = make_synthetic_gif(b"sanitized synthetic radar fixture")
    service, client = _service(tmp_path, gif)

    try:
        first = service.fetch_once(MURCIA)
        second = service.fetch_once(MURCIA)
    finally:
        client.close()

    assert first.status == "stored"
    assert second.status == "duplicate"
    assert first.raw_path == second.raw_path
    assert first.raw_path.read_bytes() == gif
    assert len(list((tmp_path / "raw").rglob("*.gif"))) == 1
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 1

    report_text = first.report_path.read_text()
    report = json.loads(report_text)
    assert report["image"]["format"] == "GIF"
    assert report["image"]["sha256"] == first.sha256
    assert report["aemetMetadata"]["formato"] == "image/gif"
    assert report["duplicateCount"] == 1
    assert report["retrievedAt"] == first.retrieved_at.isoformat().replace("+00:00", "Z")
    assert report["lastRetrievedAt"] == second.retrieved_at.isoformat().replace("+00:00", "Z")
    assert DATA_URL not in report_text
    assert METADATA_URL not in report_text
    assert FAKE_SECRET not in report_text


def test_invalid_image_creates_no_archive(tmp_path: Path) -> None:
    service, client = _service(tmp_path, b"<html>not an image</html>")

    try:
        with pytest.raises(DownloadValidationError):
            service.fetch_once(MURCIA)
    finally:
        client.close()

    assert not (tmp_path / "raw").exists()


def test_comparison_report_contains_only_safe_summaries(
    tmp_path: Path,
    make_synthetic_gif: Callable[[bytes], bytes],
) -> None:
    gif = make_synthetic_gif(b"sanitized synthetic radar fixture")
    service, client = _service(tmp_path, gif)
    try:
        outcome = service.fetch_once(MURCIA)
    finally:
        client.close()

    store = ArchiveStore(tmp_path)
    comparison_path = store.write_comparison(
        generated_at=outcome.retrieved_at,
        products=[outcome.to_dict(relative_to=tmp_path)],
    )
    text = comparison_path.read_text()

    assert outcome.sha256 in text
    assert FAKE_SECRET not in text
    assert DATA_URL not in text


def _service(
    data_dir: Path,
    data_content: bytes,
) -> tuple[IngestionService, AemetClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/red/radar/regional/mu"):
            return httpx.Response(
                200,
                json={
                    "descripcion": "exito",
                    "estado": 200,
                    "datos": DATA_URL,
                    "metadatos": METADATA_URL,
                },
            )
        if request.url == httpx.URL(DATA_URL):
            return httpx.Response(
                200,
                content=data_content,
                headers={
                    "Content-Type": "image/gif",
                    "Last-Modified": "Thu, 23 Jul 2026 12:30:00 GMT",
                },
            )
        if request.url == httpx.URL(METADATA_URL):
            return httpx.Response(
                200,
                json={"formato": "image/gif"},
                headers={"Content-Type": "application/json"},
            )
        raise AssertionError(f"Petición inesperada: {request.url}")

    http_client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )
    client = AemetClient(FAKE_SECRET, http_client=http_client)
    return IngestionService(client, ArchiveStore(data_dir)), client
