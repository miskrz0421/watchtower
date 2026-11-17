"""EngineThread running the scheduler next to the GUI."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread

from watchtower.core._scheduler import Scheduler


class EngineThread(QThread):
    """Worker thread running the scheduler, so the window never waits for the network."""

    def __init__(self, scheduler: Scheduler, parent: QObject | None = None) -> None:
        """Initialize EngineThread.

        Args:
            scheduler: Scheduler with every watcher added.
            parent: Qt parent object.
        """
        raise NotImplementedError

    def run(self) -> None:
        """Run the scheduler until `stop` is called; Qt calls this in the new thread."""
        raise NotImplementedError

    def stop(self) -> None:
        """Ask the scheduler to stop and wait until the thread ends."""
        raise NotImplementedError
