"""LogHandler sending Watchtower's log lines to the window."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from watchtower.gui._bridge import EngineBridge
from watchtower.gui._format import format_time

_WATCHTOWER_LOGGER = "watchtower"


class LogHandler(logging.Handler):
    """Emits each log record as one line through the bridge, from any thread (ADR-032)."""

    def __init__(self, bridge: EngineBridge) -> None:
        """Initialize LogHandler.

        Args:
            bridge: Bridge whose `line_logged` signal carries the lines.
        """
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        """Send one log record to the window.

        Args:
            record: Record to send.
        """
        try:
            self._bridge.line_logged.emit(_log_line(record))
        except Exception:
            self.handleError(record)


@contextmanager
def log_sent_to(bridge: EngineBridge) -> Iterator[None]:
    """Send Watchtower's own log, but not other libraries', to the bridge while the block runs.

    Args:
        bridge: Bridge that receives the lines.

    Yields:
        Nothing; the handler is removed after the block.
    """
    handler = LogHandler(bridge)
    logger = logging.getLogger(_WATCHTOWER_LOGGER)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)


def _log_line(record: logging.LogRecord) -> str:
    """Return a record as a line with its time, level and message.

    Of an exception only the type is shown: the messages in a traceback may
    contain a secret, such as a webhook address (ADR-010).

    Args:
        record: Record to format.

    Returns:
        The line.
    """
    time = format_time(datetime.fromtimestamp(record.created, UTC))
    line = f"{time} {record.levelname} {record.getMessage()}"
    error_type = record.exc_info[0] if record.exc_info else None
    return line if error_type is None else f"{line} ({error_type.__name__})"
