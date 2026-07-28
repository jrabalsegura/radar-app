#!/usr/bin/env python3
"""Comprueba que el worker sigue publicando un health.json válido y reciente."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    path = Path(os.environ.get("AEMET_HEALTH_FILE", "/data/status/health.json"))
    maximum_age = _positive_float("AEMET_HEALTH_MAX_AGE_SECONDS", 1800.0)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
            raise ValueError("schemaVersion no válido")
        products = payload.get("products")
        if not isinstance(products, list) or not products:
            raise ValueError("lista de productos ausente")
        generated_at = _parse_timestamp(payload.get("generatedAt"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"worker unhealthy: {exc}", file=sys.stderr)
        return 1

    age_seconds = (datetime.now(UTC) - generated_at).total_seconds()
    if age_seconds < -300:
        print("worker unhealthy: generatedAt está en el futuro", file=sys.stderr)
        return 1
    if age_seconds > maximum_age:
        print(
            f"worker unhealthy: health.json tiene {age_seconds:.0f}s (máximo {maximum_age:.0f}s)",
            file=sys.stderr,
        )
        return 1
    return 0


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("generatedAt ausente")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("generatedAt no contiene zona horaria")
    return parsed.astimezone(UTC)


def _positive_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    value = float(raw_value)
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
