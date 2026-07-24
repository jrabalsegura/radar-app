import pytest

from aemet_radar.errors import AemetHttpError, AemetTransportError
from aemet_radar.retry import RetryPolicy, call_with_retry


def test_retries_transient_failure_with_exponential_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise AemetTransportError("fixture")
        return "ok"

    result, used_attempts = call_with_retry(
        operation,
        RetryPolicy(max_attempts=3, initial_backoff_seconds=0.5),
        sleeper=sleeps.append,
    )

    assert result == "ok"
    assert used_attempts == 3
    assert sleeps == [0.5, 1.0]


def test_does_not_retry_authentication_error() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise AemetHttpError("fixture", 401)

    with pytest.raises(AemetHttpError):
        call_with_retry(operation, RetryPolicy(max_attempts=3), sleeper=_unexpected_sleep)

    assert attempts == 1


def test_stops_after_configured_attempts() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise AemetHttpError("fixture", 503)

    with pytest.raises(AemetHttpError):
        call_with_retry(
            operation,
            RetryPolicy(max_attempts=2, initial_backoff_seconds=1),
            sleeper=sleeps.append,
        )

    assert attempts == 2
    assert sleeps == [1]


def _unexpected_sleep(delay: float) -> None:
    raise AssertionError(f"No debía esperar {delay}")
