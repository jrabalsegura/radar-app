"""Configuración del worker obtenida exclusivamente del entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass

from aemet_radar.errors import ConfigurationError
from aemet_radar.temporal import HISTORY_HOURS

_PLACEHOLDER_VALUES = {
    "",
    "replace-with-your-own-key",
    "replace-with-your-key",
}


class Settings:
    """Configuración sensible con representación segura."""

    __slots__ = ("_api_key",)

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @classmethod
    def from_environment(cls) -> Settings:
        value = os.environ.get("AEMET_API_KEY", "").strip()
        if value in _PLACEHOLDER_VALUES:
            raise ConfigurationError(
                "Falta AEMET_API_KEY. Configúrala en el entorno o en un .env local ignorado."
            )
        return cls(api_key=value)

    @property
    def api_key(self) -> str:
        return self._api_key

    def __repr__(self) -> str:
        return "Settings(api_key=<redacted>)"


@dataclass(frozen=True, slots=True)
class OperationalSettings:
    """Parámetros no sensibles del ciclo periódico."""

    poll_interval_seconds: float = 300.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    retention_hours: float = 24.0
    history_hours: float = HISTORY_HOURS
    product_delay_seconds: float = 1.0

    @classmethod
    def from_environment(cls) -> OperationalSettings:
        return cls(
            poll_interval_seconds=_positive_float("AEMET_POLL_INTERVAL_SECONDS", 300.0),
            retry_attempts=_positive_int("AEMET_RETRY_ATTEMPTS", 3),
            retry_backoff_seconds=_non_negative_float(
                "AEMET_RETRY_BACKOFF_SECONDS",
                1.0,
            ),
            retention_hours=_positive_float("AEMET_RETENTION_HOURS", 24.0),
            history_hours=_positive_float("AEMET_HISTORY_HOURS", HISTORY_HOURS),
            product_delay_seconds=_non_negative_float(
                "AEMET_PRODUCT_DELAY_SECONDS",
                1.0,
            ),
        )


def _positive_float(name: str, default: float) -> float:
    value = _environment_float(name, default)
    if value <= 0:
        raise ConfigurationError(f"{name} debe ser mayor que cero.")
    return value


def _non_negative_float(name: str, default: float) -> float:
    value = _environment_float(name, default)
    if value < 0:
        raise ConfigurationError(f"{name} debe ser cero o mayor.")
    return value


def _positive_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} debe ser un entero.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} debe ser mayor que cero.")
    return value


def _environment_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} debe ser un número.") from exc
