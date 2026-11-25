"""Tests for the LogHandler."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

import pytest
from pytestqt.qtbot import QtBot

from watchtower.gui import EngineBridge
from watchtower.gui._log_handler import LogHandler, log_sent_to

pytestmark = pytest.mark.gui

_SECRET = "https://discord.test/webhook/secret"


@pytest.fixture
def bridge(qtbot: QtBot) -> EngineBridge:
    """Return a bridge; `qtbot` makes sure that Qt is running."""
    return EngineBridge()


@pytest.fixture
def lines(bridge: EngineBridge) -> list[str]:
    """Return the list that collects the lines the bridge emits."""
    collected: list[str] = []
    bridge.line_logged.connect(collected.append)
    return collected


def _record(message: str, *args: object) -> logging.LogRecord:
    """Return a WARNING record logged at a fixed time."""
    record = logging.LogRecord("watchtower", logging.WARNING, "file.py", 1, message, args, None)
    record.created = datetime(2026, 11, 26, 12, 0, tzinfo=UTC).timestamp()
    return record


def test_line_has_local_time_level_and_message(bridge: EngineBridge, lines: list[str]) -> None:
    """Test that a record is sent as one readable line."""
    LogHandler(bridge).handle(_record("%r failed", "Flats"))

    time = datetime(2026, 11, 26, 12, 0, tzinfo=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert lines == [f"{time} WARNING 'Flats' failed"]


def test_exception_shows_only_its_type(bridge: EngineBridge, lines: list[str]) -> None:
    """Test that the text of an exception stays out, also when another handler formatted it."""
    record = _record("Notifier failed")
    try:
        raise RuntimeError(_SECRET)
    except RuntimeError:
        record.exc_info = sys.exc_info()
    logging.Formatter().format(record)

    LogHandler(bridge).handle(record)

    assert lines[0].endswith("WARNING Notifier failed (RuntimeError)")
    assert _SECRET not in lines[0]


def test_bad_record_is_reported_by_logging(
    bridge: EngineBridge, lines: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that a record that cannot be formatted does not raise in the code that logs."""
    LogHandler(bridge).handle(_record("%d checks", "many"))

    assert lines == []
    assert "Logging error" in capsys.readouterr().err


def test_only_watchtower_is_sent_and_only_inside_the_block(
    bridge: EngineBridge, lines: list[str]
) -> None:
    """Test that other libraries and lines logged after the block are left out."""
    logger = logging.getLogger("watchtower.core")
    with log_sent_to(bridge):
        logger.warning("shown")
        logging.getLogger("httpx").warning("other library")
    logger.warning("too late")

    assert [line.rpartition(" ")[2] for line in lines] == ["shown"]
