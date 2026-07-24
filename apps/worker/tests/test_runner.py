import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx

from aemet_radar.client import DEFAULT_BASE_URL, AemetClient
from aemet_radar.manifests import ManifestPublisher
from aemet_radar.products import MURCIA
from aemet_radar.retry import RetryPolicy
from aemet_radar.runner import HistoryWorker
from aemet_radar.service import IngestionService
from aemet_radar.storage import ArchiveStore

FAKE_SECRET = "fixture-secret-that-must-never-leak"
DATA_URL = "https://opendata.aemet.es/opendata/sh/sanitized-data"
METADATA_URL = "https://opendata.aemet.es/opendata/sh/sanitized-metadata"


def test_temporary_aemet_failure_preserves_previous_manifest(tmp_path: Path) -> None:
    cycle_time = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    _archive_report(tmp_path, product_time=cycle_time - timedelta(minutes=10))
    publisher = ManifestPublisher(tmp_path)
    manifest_path = publisher.rebuild_product(
        MURCIA,
        generated_at=cycle_time - timedelta(minutes=5),
    ).path
    previous_manifest = manifest_path.read_bytes()
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(503, request=request)

    client = _client(handler)
    worker = HistoryWorker(
        IngestionService(client, ArchiveStore(tmp_path)),
        data_dir=tmp_path,
        products=(MURCIA,),
        retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
        sleeper=lambda delay: None,
    )
    try:
        result = worker.run_cycle(generated_at=cycle_time)
    finally:
        client.close()

    assert result.successful is False
    assert result.products[0].attempts == 2
    assert request_count == 2
    assert manifest_path.read_bytes() == previous_manifest
    health = json.loads((tmp_path / "status" / "health.json").read_text())
    assert health["products"][0]["status"] == "error"
    assert health["products"][0]["lastError"]["code"] == "http_error"
    assert FAKE_SECRET not in json.dumps(health)


def test_successful_cycle_archives_and_publishes(
    tmp_path: Path,
    make_synthetic_gif: Callable[[bytes], bytes],
) -> None:
    cycle_time = datetime.now(UTC)
    gif = make_synthetic_gif(b"phase 2 synthetic fixture")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(MURCIA.endpoint):
            return httpx.Response(
                200,
                json={
                    "estado": 200,
                    "datos": DATA_URL,
                    "metadatos": METADATA_URL,
                },
                request=request,
            )
        if request.url == httpx.URL(DATA_URL):
            return httpx.Response(
                200,
                content=gif,
                headers={
                    "Content-Type": "image/gif",
                    "Last-Modified": format_datetime(cycle_time),
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={"formato": "image/gif"},
            request=request,
        )

    client = _client(handler)
    worker = HistoryWorker(
        IngestionService(client, ArchiveStore(tmp_path)),
        data_dir=tmp_path,
        products=(MURCIA,),
        retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
        sleeper=lambda delay: None,
    )
    try:
        result = worker.run_cycle(generated_at=cycle_time)
    finally:
        client.close()

    assert result.successful is True
    assert result.products[0].status == "stored"
    manifest = json.loads((tmp_path / "radar" / MURCIA.id / "manifest.json").read_text())
    assert len(manifest["frames"]) == 1
    assert manifest["frames"][0]["timeSource"] == "productTime"
    assert (tmp_path / "radar" / "index.json").is_file()
    assert (tmp_path / "status" / "health.json").is_file()


def test_first_failed_cycle_still_publishes_empty_manifest(tmp_path: Path) -> None:
    cycle_time = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"estado": 404, "descripcion": "sin datos"},
            request=request,
        )

    client = _client(handler)
    worker = HistoryWorker(
        IngestionService(client, ArchiveStore(tmp_path)),
        data_dir=tmp_path,
        products=(MURCIA,),
        retry_policy=RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
        sleeper=lambda delay: None,
    )
    try:
        result = worker.run_cycle(generated_at=cycle_time)
    finally:
        client.close()

    assert result.successful is False
    manifest_path = tmp_path / "radar" / MURCIA.id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["frames"] == []
    health = json.loads((tmp_path / "status" / "health.json").read_text())
    assert health["products"][0]["status"] == "error"
    assert health["products"][0]["dataStatus"] == "no-data"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> AemetClient:
    return AemetClient(
        FAKE_SECRET,
        http_client=httpx.Client(
            base_url=DEFAULT_BASE_URL,
            transport=httpx.MockTransport(handler),
        ),
    )


def _archive_report(data_dir: Path, *, product_time: datetime) -> None:
    digest = "1" * 64
    directory = data_dir / "raw" / MURCIA.id / "2026" / "07" / "24"
    directory.mkdir(parents=True)
    raw_path = directory / f"{digest}.gif"
    report_path = directory / f"{digest}.json"
    raw_path.write_bytes(b"GIF89a synthetic")
    report = {
        "product": {"id": MURCIA.id},
        "retrievedAt": _isoformat(product_time + timedelta(minutes=1)),
        "image": {"sha256": digest},
        "productTime": {"status": "candidate", "value": _isoformat(product_time)},
        "files": {
            "raw": raw_path.relative_to(data_dir).as_posix(),
            "report": report_path.relative_to(data_dir).as_posix(),
        },
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
