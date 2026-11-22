"""Initial statuses shared by the window and the tray icon."""

from __future__ import annotations

from watchtower.core._scheduler import Scheduler
from watchtower.core._states import WatcherStatus


def initial_statuses(
    scheduler: Scheduler, statuses: list[WatcherStatus] | None
) -> list[WatcherStatus]:
    """Return the statuses read once by the app, or read them for a standalone widget.

    Args:
        scheduler: Scheduler holding the watchers.
        statuses: Statuses read before the engine thread started; None when a
            widget is built on its own, outside `run_gui`.

    Returns:
        Statuses to show at startup.
    """
    return scheduler.statuses() if statuses is None else statuses
