"""Loading watchers from a YAML config file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from watchtower.core.builder import WatcherBuilder


@dataclass(frozen=True)
class Config:
    """Contents of a config file, ready to be turned into watchers.

    Attributes:
        database: SQLite file for snapshots and history, or None if the file
            has no `database` key. A relative path starts at the config file's
            folder.
        watchers: One builder per entry under `watchers`, in file order. The
            caller adds the store and the event bus, then calls `build`.
    """

    database: Path | None
    watchers: tuple[WatcherBuilder, ...]


def load_config(path: Path) -> Config:
    """Read a YAML config file.

    Sources, differs, notifiers and filters are created by name through the
    registry and handed to a WatcherBuilder, the same one the Python API uses
    (see ADR-018). The file format is described in ADR-017 and shown in
    `examples/config.yaml`.

    Args:
        path: Path to the YAML file.

    Returns:
        The database path and one builder per watcher.

    Raises:
        ConfigError: If the file is missing, is not valid YAML, lacks a
            required key, names an unknown plugin or repeats a watcher name.
    """
    raise NotImplementedError
