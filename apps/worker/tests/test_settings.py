import pytest

from aemet_radar.errors import ConfigurationError
from aemet_radar.settings import Settings


def test_settings_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEMET_API_KEY", raising=False)

    with pytest.raises(ConfigurationError):
        Settings.from_environment()


def test_settings_repr_redacts_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "fixture-secret-that-must-never-leak"
    monkeypatch.setenv("AEMET_API_KEY", secret)

    settings = Settings.from_environment()

    assert settings.api_key == secret
    assert secret not in repr(settings)
