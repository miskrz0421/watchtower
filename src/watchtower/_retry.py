"""Decorators for functions that may fail or take long."""

from __future__ import annotations

import time
from collections.abc import Callable


def retry[**P, T](
    *,
    on: type[Exception] | tuple[type[Exception], ...],
    times: int = 3,
    first_delay: float = 0.5,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Make a function try again when it fails with a temporary error.

    Args:
        on: Errors worth another try; any other error is raised at once.
        times: How many times the function is called at most.
        first_delay: Seconds to wait before the second try.
        backoff: How many times longer each next wait is.
        sleep: Function that waits; tests pass one that only records the delays.

    Returns:
        Decorator for the function.
    """
    raise NotImplementedError


def timed[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    """Log at DEBUG how long every call of a function takes, also when it fails.

    Args:
        function: Function to measure.

    Returns:
        The decorated function.
    """
    raise NotImplementedError
