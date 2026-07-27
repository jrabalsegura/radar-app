"""Estado operativo público derivado de manifiestos y ciclos de consulta."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from aemet_radar.history import isoformat_utc, parse_utc_datetime
from aemet_radar.manifests import ManifestPublisher
from aemet_radar.products import RadarProduct
from aemet_radar.storage import atomic_write_json


@dataclass(frozen=True, slots=True)
class PollObservation:
    status: Literal["success", "no-data", "error"]
    checked_at: datetime
    attempts: int
    outcome_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, object] | None = None
    diagnostic_report: str | None = None


class HealthPublisher:
    def __init__(self, data_dir: Path, manifests: ManifestPublisher) -> None:
        self.data_dir = data_dir.resolve()
        self.manifests = manifests

    def publish(
        self,
        products: tuple[RadarProduct, ...],
        *,
        generated_at: datetime,
        polls: dict[str, PollObservation] | None = None,
    ) -> Path:
        observations = polls or {}
        previous = _load_json_object(self.path)
        previous_products = _previous_products(previous)
        product_states = [
            self._product_state(
                product,
                generated_at=generated_at,
                observation=observations.get(product.id),
                previous=previous_products.get(product.id),
            )
            for product in products
        ]
        statuses = {state["status"] for state in product_states}
        if "error" in statuses or "delayed" in statuses:
            overall_status = "degraded"
        elif statuses == {"no-data"}:
            overall_status = "no-data"
        else:
            overall_status = "ok"

        atomic_write_json(
            self.path,
            {
                "schemaVersion": 1,
                "generatedAt": isoformat_utc(generated_at),
                "status": overall_status,
                "products": product_states,
            },
        )
        return self.path

    @property
    def path(self) -> Path:
        return self.data_dir / "status" / "health.json"

    def _product_state(
        self,
        product: RadarProduct,
        *,
        generated_at: datetime,
        observation: PollObservation | None,
        previous: dict[str, object] | None,
    ) -> dict[str, object]:
        manifest = self.manifests.read_product(product)
        latest_time = _optional_string(manifest, "latestFrameTime")
        latest_product_time = _optional_string(manifest, "latestProductTime")
        time_basis = _optional_string(manifest, "timeBasis")
        frames = manifest.get("frames") if manifest is not None else None
        frame_count = len(frames) if isinstance(frames, list) else 0
        statistics = manifest.get("statistics") if manifest is not None else None
        archive_count = (
            statistics.get("archivedFrames")
            if isinstance(statistics, dict) and isinstance(statistics.get("archivedFrames"), int)
            else 0
        )

        age_seconds: int | None = None
        if latest_time is not None:
            age_seconds = max(
                0,
                int((generated_at - parse_utc_datetime(latest_time)).total_seconds()),
            )
        stale_after_seconds = product.cadence_minutes * 2 * 60
        if latest_time is None:
            data_status = "no-data"
        elif age_seconds is not None and age_seconds > stale_after_seconds:
            data_status = "delayed"
        else:
            data_status = "current"
        previous_status = _optional_string(previous, "status")
        if observation is not None and observation.status == "error":
            status = "error"
        elif observation is not None and observation.status == "no-data":
            status = "no-data"
        elif observation is None and previous_status == "error":
            status = "error"
        else:
            status = data_status

        previous_last_poll = _optional_string(previous, "lastPollAt")
        previous_last_success = _optional_string(previous, "lastSuccessAt")
        previous_error = previous.get("lastError") if previous is not None else None
        previous_attempts = previous.get("attempts") if previous is not None else None
        previous_outcome = _optional_string(previous, "lastOutcome")
        last_poll_at = (
            isoformat_utc(observation.checked_at) if observation is not None else previous_last_poll
        )
        last_success_at: str | None
        last_error: object | None
        if observation is not None and observation.status == "success":
            last_success_at = isoformat_utc(observation.checked_at)
            last_error = None
        elif observation is not None and observation.status == "no-data":
            last_success_at = previous_last_success
            last_error = None
        elif observation is not None:
            last_success_at = previous_last_success
            error_payload: dict[str, object] = {
                "code": observation.error_code,
                "message": observation.error_message,
            }
            if observation.error_details is not None:
                error_payload["details"] = observation.error_details
            if observation.diagnostic_report is not None:
                error_payload["diagnosticReport"] = observation.diagnostic_report
            last_error = error_payload
        else:
            last_success_at = previous_last_success
            last_error = previous_error

        return {
            "id": product.id,
            "label": product.label,
            "status": status,
            "dataStatus": data_status,
            "lastPollAt": last_poll_at,
            "lastSuccessAt": last_success_at,
            "lastFrameTime": latest_time,
            "latestProductTime": latest_product_time,
            "timeBasis": time_basis,
            "ageSeconds": age_seconds,
            "staleAfterSeconds": stale_after_seconds,
            "publishableFrames": frame_count,
            "archivedFrames": archive_count,
            "attempts": (observation.attempts if observation is not None else previous_attempts),
            "lastOutcome": (
                observation.outcome_status if observation is not None else previous_outcome
            ),
            "lastError": last_error,
            "manifestUrl": f"/radar/{product.id}/manifest.json",
        }


def _load_json_object(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, object], payload)


def _previous_products(
    health: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    if health is None:
        return {}
    products = health.get("products")
    if not isinstance(products, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for item in products:
        if not isinstance(item, dict):
            continue
        product_id = item.get("id")
        if isinstance(product_id, str):
            result[product_id] = cast(dict[str, object], item)
    return result


def _optional_string(
    payload: dict[str, object] | None,
    key: str,
) -> str | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, str) else None
