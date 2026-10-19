"""Base Notifier interface implementing the Adapter pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod

from watchtower.models import ChangeEvent


class Notifier(ABC):
    """Abstract interface for dispatching change events to destinations."""

    @abstractmethod
    def send(self, event: ChangeEvent) -> None:
        """Send a ChangeEvent to the configured notification target.

        Args:
            event: The change event containing filtered changes and summary.

        Raises:
            NotifyError: If sending the notification fails.
        """
