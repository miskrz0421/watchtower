"""Commands the GUI sends to the running engine (Command pattern, see ADR-023)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pause:
    """Stop checking a watcher until it is resumed."""

    watcher_name: str


@dataclass(frozen=True)
class Resume:
    """Check a paused or disabled watcher again, starting now."""

    watcher_name: str


@dataclass(frozen=True)
class CheckNow:
    """Check a watcher at once, without waiting for its interval."""

    watcher_name: str


@dataclass(frozen=True)
class ReloadConfig:
    """Read the config file again and replace the watchers with the ones in it."""


type Command = Pause | Resume | CheckNow | ReloadConfig
