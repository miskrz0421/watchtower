"""Decorators for functions that may fail or take long."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable

_logger = logging.getLogger(__name__)


def _sleep(seconds: float) -> None:
    """Default sleep function of the retry decorator, ment to be patched by tests.

    Args:
        seconds: Seconds to sleep for.
    """
    time.sleep(seconds)


def retry[**P, T](
    *,
    on: type[Exception] | tuple[type[Exception], ...],
    times: int = 3,
    first_delay: float = 0.5,
    backoff: float = 2.0,
    sleep: Callable[[float], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Make a function try again when it fails with a temporary error.

    Args:
        on: Errors worth another try; any other error is raised at once.
        times: How many times the function is called at most; must be positive.
        first_delay: Seconds to wait before the second try; must be non-negative.
        backoff: How many times longer each next wait is; must be at least 1.
        sleep: Function that waits; tests pass one that only records the delays.

    Returns:
        Decorator for the function.

    Raises:
        ValueError: If `times`, `first_delay` or `backoff` is invalid.
    """
    if times <= 0:
        msg = f"times has to be greater than 0, got {times}"
        raise ValueError(msg)
    if first_delay < 0:
        msg = f"first_delay has to be non-negative, got {first_delay}"
        raise ValueError(msg)
    if backoff < 1:
        msg = f"backoff has to be at least 1, got {backoff}"
        raise ValueError(msg)

    def decorator(function: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            wait = sleep if sleep is not None else _sleep
            delay = first_delay
            for _ in range(times - 1):
                try:
                    return function(*args, **kwargs)
                except on:
                    wait(delay)
                    delay *= backoff
            return function(*args, **kwargs)

        return wrapper

    return decorator


def timed[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    """Log at DEBUG how long every call of a function takes, also when it fails.

    Args:
        function: Function to measure.

    Returns:
        The decorated function.
    """

    @functools.wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            _logger.debug("%s took %.3fs", function.__qualname__, elapsed)

    return wrapper
