"""Configuración del worker obtenida exclusivamente del entorno."""

from __future__ import annotations

import os

from aemet_radar.errors import ConfigurationError

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
