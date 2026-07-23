"""Orquestación de una ingesta puntual."""

from __future__ import annotations

from aemet_radar.client import AemetClient
from aemet_radar.inspection import inspect_gif, resolve_product_time
from aemet_radar.models import DownloadedProduct, FetchOutcome
from aemet_radar.products import RadarProduct
from aemet_radar.storage import ArchiveStore


class IngestionService:
    def __init__(self, client: AemetClient, store: ArchiveStore) -> None:
        self._client = client
        self._store = store

    def fetch_once(self, product: RadarProduct) -> FetchOutcome:
        downloaded = self._client.fetch_product(product)
        inspection = inspect_gif(
            downloaded.content,
            downloaded.data_headers.get("content-type"),
        )
        product_time = resolve_product_time(
            headers=downloaded.data_headers,
            internal_metadata=inspection.internal_metadata,
            resource_name=downloaded.resource_name,
            retrieved_at=downloaded.retrieved_at,
            cadence_minutes=product.cadence_minutes,
        )
        report = _build_report(downloaded, inspection.to_dict(), product_time.to_dict())
        archive = self._store.archive(
            product=product,
            content=downloaded.content,
            sha256=inspection.sha256,
            retrieved_at=downloaded.retrieved_at,
            report=report,
        )
        return FetchOutcome(
            product_id=product.id,
            status=archive.status,
            sha256=inspection.sha256,
            raw_path=archive.raw_path,
            report_path=archive.report_path,
            retrieved_at=downloaded.retrieved_at,
            inspection=inspection.summary(),
            product_time=product_time,
        )


def _build_report(
    downloaded: DownloadedProduct,
    image: dict[str, object],
    product_time: dict[str, object],
) -> dict[str, object]:
    product = downloaded.product
    return {
        "schemaVersion": 1,
        "product": {
            "id": product.id,
            "label": product.label,
            "kind": product.kind.value,
            "aemetCode": product.aemet_code,
            "endpoint": product.endpoint,
            "cadenceMinutes": product.cadence_minutes,
        },
        "retrievedAt": downloaded.retrieved_at.isoformat().replace("+00:00", "Z"),
        "http": {
            "gateway": {
                "status": downloaded.gateway_status,
                "headers": downloaded.gateway_headers,
            },
            "data": {
                "status": downloaded.data_status,
                "headers": downloaded.data_headers,
            },
            "metadata": {
                "status": downloaded.metadata.status,
                "headers": downloaded.metadata.headers,
                "errorCode": downloaded.metadata.error_code,
            },
        },
        "aemetMetadata": downloaded.metadata.payload,
        "image": image,
        "productTime": product_time,
    }
