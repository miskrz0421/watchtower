"""Tests for the retry and timed decorators."""

from __future__ import annotations

import logging
import re

import pytest

from watchtower import _retry
from watchtower._retry import _sleep, retry, timed


def _double(value: int) -> int:
    """Return twice the given number."""
    return value * 2


def test_sleep_delegates_to_time_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the default wait function sleeps for the requested time."""
    waited: list[float] = []
    monkeypatch.setattr(_retry.time, "sleep", waited.append)

    _sleep(1.25)

    assert waited == [1.25]


def test_retry_returns_result_without_waiting_when_call_succeeds() -> None:
    """Test that a successful call passes its arguments through and never sleeps."""
    delays: list[float] = []
    calls: list[tuple[int, str]] = []

    @retry(on=ValueError, sleep=delays.append)
    def work(number: int, label: str) -> str:
        """Return a labelled number."""
        calls.append((number, label))
        return f"{label}{number}"

    assert work(7, "item") == "item7"
    assert calls == [(7, "item")]
    assert delays == []


def test_retry_retries_with_growing_delays_until_success() -> None:
    """Test that retryable errors are waited out with exponential backoff."""
    delays: list[float] = []
    attempts = 0

    @retry(on=ValueError, times=3, first_delay=0.25, sleep=delays.append)
    def work() -> str:
        """Fail twice, then succeed."""
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("try again")
        return "done"

    assert work() == "done"
    assert attempts == 3
    assert delays == [0.25, 0.5]


def test_retry_reraises_the_error_after_the_last_attempt() -> None:
    """Test that exhausting the attempts re-raises the last error, with no extra wait."""
    delays: list[float] = []
    attempts = 0

    @retry(on=ValueError, times=3, first_delay=0.5, backoff=3.0, sleep=delays.append)
    def work() -> None:
        """Always fail."""
        nonlocal attempts
        attempts += 1
        raise ValueError("still broken")

    with pytest.raises(ValueError, match="still broken"):
        work()

    assert attempts == 3
    assert delays == [0.5, 1.5]


def test_retry_does_not_catch_other_errors() -> None:
    """Test that an error outside `on` is raised at once, without another try."""
    delays: list[float] = []
    attempts = 0

    @retry(on=ValueError, sleep=delays.append)
    def work() -> None:
        """Fail with a non-retryable error."""
        nonlocal attempts
        attempts += 1
        raise TypeError("wrong type")

    with pytest.raises(TypeError, match="wrong type"):
        work()

    assert attempts == 1
    assert delays == []


def test_retry_accepts_a_tuple_of_errors() -> None:
    """Test that any of several error types can trigger a retry."""
    delays: list[float] = []
    attempts = 0

    @retry(on=(ValueError, KeyError), sleep=delays.append)
    def work() -> str:
        """Fail with two different retryable errors, then succeed."""
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise KeyError("missing")
        if attempts == 2:
            raise ValueError("bad value")
        return "done"

    assert work() == "done"
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_retry_resolves_the_module_sleep_on_each_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that patching `_sleep` reaches a decorator applied before the patch."""
    delays: list[float] = []
    monkeypatch.setattr(_retry, "_sleep", delays.append)
    attempts = 0

    @retry(on=ValueError)
    def work() -> str:
        """Fail once, then succeed."""
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("flaky")
        return "done"

    assert work() == "done"
    assert delays == [0.5]


def test_retry_prefers_an_explicit_sleep_over_the_module_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a passed-in sleep function is used instead of `_sleep`."""
    module_delays: list[float] = []
    monkeypatch.setattr(_retry, "_sleep", module_delays.append)
    delays: list[float] = []
    attempts = 0

    @retry(on=ValueError, sleep=delays.append)
    def work() -> str:
        """Fail once, then succeed."""
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("flaky")
        return "done"

    assert work() == "done"
    assert delays == [0.5]
    assert module_delays == []


@pytest.mark.parametrize("times", [0, -1])
def test_retry_rejects_non_positive_attempt_counts(times: int) -> None:
    """Test that a non-positive number of attempts is invalid."""
    with pytest.raises(ValueError, match="times has to be greater than 0"):
        retry(on=ValueError, times=times)


@pytest.mark.parametrize("first_delay", [-0.25, -1.0])
def test_retry_rejects_negative_first_delay(first_delay: float) -> None:
    """Test that a negative wait before the first retry is invalid."""
    with pytest.raises(ValueError, match="first_delay has to be non-negative"):
        retry(on=ValueError, first_delay=first_delay)


@pytest.mark.parametrize("backoff", [0.0, 0.5])
def test_retry_rejects_a_shrinking_backoff(backoff: float) -> None:
    """Test that a factor which shortens the waits is invalid."""
    with pytest.raises(ValueError, match="backoff has to be at least 1"):
        retry(on=ValueError, backoff=backoff)


def test_retry_accepts_a_zero_delay_and_a_unit_backoff() -> None:
    """Test the boundary values: instant retries with a constant delay."""
    delays: list[float] = []
    attempts = 0

    @retry(on=ValueError, times=3, first_delay=0.0, backoff=1.0, sleep=delays.append)
    def work() -> str:
        """Fail twice, then succeed."""
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("try again")
        return "done"

    assert work() == "done"
    assert delays == [0.0, 0.0]


def test_retry_asserts_when_no_attempt_was_made(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the defensive guard if the attempt loop cannot run."""
    monkeypatch.setattr(_retry, "range", lambda *_: (), raising=False)

    @retry(on=ValueError, times=1)
    def work() -> None:
        """Do nothing; the guard should fire before it is called."""

    with pytest.raises(AssertionError, match="unreachable"):
        work()


def test_retry_preserves_the_wrapped_functions_metadata() -> None:
    """Test that functools.wraps keeps the name and docstring of the function."""

    @retry(on=ValueError)
    def work(value: int) -> int:
        """Double a number."""
        return value * 2

    assert work.__name__ == "work"
    assert work.__doc__ == "Double a number."
    assert work(3) == 6


def test_timed_returns_the_result_and_preserves_metadata() -> None:
    """Test that the timing wrapper is transparent to callers."""
    measured = timed(_double)

    assert measured(4) == 8
    assert measured.__name__ == "_double"
    assert measured.__doc__ == "Return twice the given number."


def test_timed_logs_the_duration_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    """Test that a successful call logs its elapsed time at DEBUG."""
    with caplog.at_level(logging.DEBUG, logger="watchtower._retry"):
        assert timed(_double)(6) == 12

    assert [record.name for record in caplog.records] == ["watchtower._retry"]
    assert [record.levelno for record in caplog.records] == [logging.DEBUG]
    assert re.fullmatch(r"_double took \d+\.\d{3}s", caplog.messages[0])


def test_timed_logs_the_duration_even_when_the_call_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that the finally clause logs a call that raises an error."""

    def fail() -> None:
        """Fail on purpose."""
        raise RuntimeError("boom")

    with (
        caplog.at_level(logging.DEBUG, logger="watchtower._retry"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        timed(fail)()

    assert len(caplog.records) == 1
    assert "fail took" in caplog.messages[0]
