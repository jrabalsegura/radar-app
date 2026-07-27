import pytest

from aemet_radar.errors import ConfigurationError
from aemet_radar.settings import OperationalSettings, Settings


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


def test_operational_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEMET_POLL_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("AEMET_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("AEMET_RETRY_BACKOFF_SECONDS", "0.25")
    monkeypatch.setenv("AEMET_RETENTION_HOURS", "36")
    monkeypatch.setenv("AEMET_HISTORY_HOURS", "2.5")
    monkeypatch.setenv("AEMET_PRODUCT_DELAY_SECONDS", "0.75")

    settings = OperationalSettings.from_environment()

    assert settings.poll_interval_seconds == 120
    assert settings.retry_attempts == 4
    assert settings.retry_backoff_seconds == 0.25
    assert settings.retention_hours == 36
    assert settings.history_hours == 2.5
    assert settings.product_delay_seconds == 0.75


def test_operational_settings_default_to_three_hours_fifty_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AEMET_HISTORY_HOURS", raising=False)

    assert OperationalSettings.from_environment().history_hours == 23 / 6
