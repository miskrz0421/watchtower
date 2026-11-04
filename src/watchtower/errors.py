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
