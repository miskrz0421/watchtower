"""Loading watchers from a YAML config file."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from watchtower._errors import ConfigError
from watchtower._registry import (
    create_differ,
    create_notifier,
    create_source,
    list_plugins,
)
from watchtower.config._filters import build_filter
from watchtower.config._intervals import parse_interval
from watchtower.core._builder import WatcherBuilder

_ALLOWED_TOP_LEVEL_KEYS = {"database", "watchers"}
_ALLOWED_WATCHER_KEYS = {"name", "source", "diff", "interval", "filters", "notify"}

type _YamlMapping = dict[str, Any]
type _WatcherConfigDict = dict[str, Any]


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


def _read_yaml(path: Path) -> _YamlMapping:
    """Read and parse a YAML configuration file.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed YAML mapping.

    Raises:
        ConfigError: If the file does not exist, cannot be read, or is not a mapping.
    """
    if not path.is_file():
        msg = f"Config file not found: {path}"
        raise ConfigError(msg)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as err:
        msg = f"Invalid YAML in {path}: {err}"
        raise ConfigError(msg) from err
    except OSError as err:
        msg = f"Cannot read config file {path}: {err}"
        raise ConfigError(msg) from err
    if not isinstance(data, dict):
        msg = f"Config file {path} must contain a mapping"
        raise ConfigError(msg)
    return data


def _resolve_database(raw_database: object, config_dir: Path) -> Path | None:
    """Resolve database path from configuration data.

    Args:
        raw_database: Raw database configuration value from the config file.
        config_dir: Directory containing the config file.

    Returns:
        The resolved absolute or config-relative Path, or None if omitted.

    Raises:
        ConfigError: If the database path is not valid text or is empty.
    """
    if raw_database is None:
        return None
    if not isinstance(raw_database, str) or not raw_database:
        msg = f"Config file key 'database' must be a non-empty string, got {raw_database!r}"
        raise ConfigError(msg)
    path = Path(raw_database)
    return path if path.is_absolute() else config_dir / path


def _build_component[T](
    key_name: str,
    plugin_kind: str,
    factory: Callable[..., T],
    watcher_name: str,
    config: object,
) -> T:
    """Instantiate a plugin component (source, differ, notifier) from config mapping.

    Args:
        key_name: Configuration key name (e.g. 'source', 'diff', 'notify').
        plugin_kind: Registry plugin category (e.g. 'source', 'differ', 'notifier').
        factory: Registry factory function to instantiate the plugin.
        watcher_name: Name of the watcher for error messages.
        config: Component configuration mapping.

    Returns:
        The instantiated plugin object.

    Raises:
        ConfigError: If configuration is invalid or names an unknown plugin.
    """
    if not isinstance(config, dict):
        msg = f"Watcher {watcher_name!r} key {key_name!r}: must be a mapping"
        raise ConfigError(msg)
    if "type" not in config:
        msg = f"Watcher {watcher_name!r} key {key_name!r}: missing required key 'type'"
        raise ConfigError(msg)
    plugin_type = config["type"]
    if not isinstance(plugin_type, str):
        msg = f"Watcher {watcher_name!r} key {key_name!r}: 'type' must be a string"
        raise ConfigError(msg)

    registered = list_plugins(plugin_kind).get(plugin_kind, [])
    if plugin_type not in registered:
        msg = (
            f"Watcher {watcher_name!r} key {key_name!r}: "
            f"unknown {plugin_kind} plugin {plugin_type!r}"
        )
        raise ConfigError(msg)

    params = {k: v for k, v in config.items() if k != "type"}
    try:
        return factory(plugin_type, **params)
    except (TypeError, ValueError) as err:
        msg = f"Watcher {watcher_name!r} key {key_name!r}: {err}"
        raise ConfigError(msg) from err


def _watcher_name(entry: _WatcherConfigDict, seen_names: set[str]) -> str:
    """Validate and return the watcher name, ensuring it is unique."""
    if "name" not in entry:
        msg = "Watcher entry missing required key 'name'"
        raise ConfigError(msg)
    name = entry["name"]
    if not isinstance(name, str) or not name.strip():
        msg = f"Watcher key 'name' must be a non-empty string, got {name!r}"
        raise ConfigError(msg)
    if name in seen_names:
        msg = f"Watcher {name!r} key 'name': duplicate watcher name"
        raise ConfigError(msg)
    seen_names.add(name)
    return name


def _check_watcher_keys(name: str, entry: _WatcherConfigDict) -> None:
    """Validate allowed keys and ensure required source and diff keys are present."""
    for key in entry:
        if key not in _ALLOWED_WATCHER_KEYS:
            msg = f"Watcher {name!r} has unknown key {key!r}"
            raise ConfigError(msg)
    if "source" not in entry:
        msg = f"Watcher {name!r} missing required key 'source'"
        raise ConfigError(msg)
    if "diff" not in entry:
        msg = f"Watcher {name!r} missing required key 'diff'"
        raise ConfigError(msg)


def _add_interval(builder: WatcherBuilder, name: str, entry: _WatcherConfigDict) -> None:
    """Configure check interval on the builder if specified."""
    if "interval" not in entry:
        return
    try:
        builder.every(parse_interval(entry["interval"]))
    except ConfigError as err:
        msg = f"Watcher {name!r} key 'interval': {err}"
        raise ConfigError(msg) from err


def _add_filters(builder: WatcherBuilder, name: str, entry: _WatcherConfigDict) -> None:
    """Configure filter chain on the builder if specified."""
    if "filters" not in entry:
        return
    filters_raw = entry["filters"]
    if not isinstance(filters_raw, list):
        msg = f"Watcher {name!r} key 'filters': must be a list"
        raise ConfigError(msg)
    for filter_entry in filters_raw:
        builder.only_if(build_filter(name, filter_entry))


def _add_notifiers(builder: WatcherBuilder, name: str, entry: _WatcherConfigDict) -> None:
    """Configure notifiers on the builder if specified."""
    if "notify" not in entry:
        return
    notify_raw = entry["notify"]
    if not isinstance(notify_raw, list):
        msg = f"Watcher {name!r} key 'notify': must be a list"
        raise ConfigError(msg)
    for notifier_cfg in notify_raw:
        builder.notify(_build_component("notify", "notifier", create_notifier, name, notifier_cfg))


def _build_watcher(entry: object, seen_names: set[str]) -> WatcherBuilder:
    """Build a WatcherBuilder from a single watcher configuration entry.

    Args:
        entry: Watcher configuration mapping.
        seen_names: Set of already seen watcher names for duplicate detection.

    Returns:
        Configured WatcherBuilder.

    Raises:
        ConfigError: If the watcher configuration has missing or invalid keys.
    """
    if not isinstance(entry, dict):
        msg = "Watcher entry must be a mapping"
        raise ConfigError(msg)

    name = _watcher_name(entry, seen_names)
    _check_watcher_keys(name, entry)

    source = _build_component("source", "source", create_source, name, entry["source"])
    differ = _build_component("diff", "differ", create_differ, name, entry["diff"])
    builder = WatcherBuilder(name).source(source).diff(differ)

    _add_interval(builder, name, entry)
    _add_filters(builder, name, entry)
    _add_notifiers(builder, name, entry)

    return builder


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
    raw_config = _read_yaml(path)
    for key in raw_config:
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            msg = f"Config file has unknown key {key!r}"
            raise ConfigError(msg)

    database = _resolve_database(raw_config.get("database"), path.parent)
    if "watchers" not in raw_config:
        msg = f"Config file {path} lacks required key 'watchers'"
        raise ConfigError(msg)
    watchers_raw = raw_config["watchers"]
    if not isinstance(watchers_raw, list):
        msg = f"Config file {path} key 'watchers' must be a list"
        raise ConfigError(msg)

    seen_names: set[str] = set()
    builders = [_build_watcher(entry, seen_names) for entry in watchers_raw]

    return Config(database=database, watchers=tuple(builders))
