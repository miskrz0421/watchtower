"""Fixtures shared by the tests of the built-in data sources."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from watchtower import _retry


@pytest.fixture(autouse=True)
def retry_delays(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Collect the retry waits instead of really sleeping during source tests.

    `retry` resolves `_sleep` on each call, so patching the module attribute
    reaches the already-decorated `HttpSource.fetch`. Tests may request this
    fixture to assert on the delays.
    """
    delays: list[float] = []

    def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(_retry, "_sleep", fake_sleep)
    yield delays
