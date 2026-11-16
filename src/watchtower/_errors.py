"""Exception hierarchy for the Watchtower framework."""

from __future__ import annotations


class WatchtowerError(Exception):
    """Base class for all exceptions raised by Watchtower."""


class SourceError(WatchtowerError):
    """Raised when an error occurs while fetching data from a source."""


class ParseError(WatchtowerError):
    """Raised when an error occurs while parsing content from a source."""


class NotifyError(WatchtowerError):
    """Raised when an error occurs while dispatching a notification."""


class ConfigError(WatchtowerError):
    """Raised when a config file or a watcher description is invalid."""


class StorageError(WatchtowerError):
    """Raised when saved state cannot be read from or written to storage."""
