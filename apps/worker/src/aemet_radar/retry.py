"""Reintentos limitados para fallos transitorios de AEMET."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from aemet_radar.errors import (
    AemetApiStatusError,
    AemetHttpError,
    AemetRadarError,
    AemetTransportError,
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    multiplier: float = 2.0
    maximum_backoff_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts debe ser mayor que cero.")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds no puede ser negativo.")
        if self.multiplier < 1:
            raise ValueError("multiplier debe ser uno o mayor.")
        if self.maximum_backoff_seconds < 0:
            raise ValueError("maximum_backoff_seconds no puede ser negativo.")


def call_with_retry[T](
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Ejecuta una operación y devuelve su resultado junto al número de intentos."""

    attempt = 0
    while True:
        attempt += 1
        try:
            return operation(), attempt
        except AemetRadarError as exc:
            if attempt >= policy.max_attempts or not is_retryable(exc):
                raise
            delay = min(
                policy.initial_backoff_seconds * policy.multiplier ** (attempt - 1),
                policy.maximum_backoff_seconds,
            )
            sleeper(delay)


def is_retryable(error: AemetRadarError) -> bool:
    if isinstance(error, AemetTransportError):
        return True
    if isinstance(error, AemetHttpError):
        return error.status_code in {408, 425, 429} or error.status_code >= 500
    if isinstance(error, AemetApiStatusError):
        return error.status_code == 429 or error.status_code >= 500
    return False
