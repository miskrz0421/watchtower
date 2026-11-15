"""Loading watchers from a YAML config file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from watchtower.config.intervals import parse_interval
from watchtower.core.builder import WatcherBuilder
from watchtower.diffs.base import Differ
from watchtower.errors import ConfigError
from watchtower.filters.base import Filter
from watchtower.notifiers.base import Notifier
from watchtower.registry import (
    create_differ,
    create_filter,
    create_notifier,
    create_source,
)
from watchtower.sources.base import Source

_ALLOWED_TOP_LEVEL_KEYS = {"database", "watchers"}
_ALLOWED_WATCHER_KEYS = {"name", "source", "diff", "interval", "filters", "notify"}


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


def _read_yaml(path: Path) -> dict[str, Any]:
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


def _resolve_database(data: dict[str, Any], config_dir: Path) -> Path | None:
    """Resolve database path from configuration data.

    Args:
        data: Parsed configuration dictionary.
        config_dir: Directory containing the config file.

    Returns:
        The resolved absolute or config-relative Path, or None if omitted.

    Raises:
        ConfigError: If the database path is not valid text.
    """
    if "database" not in data or data["database"] is None:
        return None
    raw = data["database"]
    if not isinstance(raw, str) or not raw.strip():
        msg = f"Config file key 'database' must be a non-empty string, got {raw!r}"
        raise ConfigError(msg)
    raw_path = Path(raw)
    return raw_path if raw_path.is_absolute() else config_dir / raw_path


def _build_source(watcher_name: str, config: Any) -> Source:
    """Instantiate a Source from its configuration mapping.

    Args:
        watcher_name: Name of the watcher for error messages.
        config: Source configuration mapping.

    Returns:
        The instantiated Source.

    Raises:
        ConfigError: If configuration is invalid or names an unknown plugin.
    """
    if not isinstance(config, dict):
        msg = f"Watcher {watcher_name!r} key 'source': must be a mapping"
        raise ConfigError(msg)
    if "type" not in config:
        msg = f"Watcher {watcher_name!r} key 'source': missing required key 'type'"
        raise ConfigError(msg)
    plugin_type = config["type"]
    if not isinstance(plugin_type, str):
        msg = f"Watcher {watcher_name!r} key 'source': 'type' must be a string"
        raise ConfigError(msg)
    params = {k: v for k, v in config.items() if k != "type"}
    try:
        return create_source(plugin_type, **params)
    except KeyError as err:
        msg = f"Watcher {watcher_name!r} key 'source': unknown source plugin {plugin_type!r}"
        raise ConfigError(msg) from err
    except (TypeError, ValueError) as err:
        msg = f"Watcher {watcher_name!r} key 'source': {err}"
        raise ConfigError(msg) from err


def _build_differ(watcher_name: str, config: Any) -> Differ:
    """Instantiate a Differ from its configuration mapping.

    Args:
        watcher_name: Name of the watcher for error messages.
        config: Differ configuration mapping.

    Returns:
        The instantiated Differ.

    Raises:
        ConfigError: If configuration is invalid or names an unknown plugin.
    """
    if not isinstance(config, dict):
        msg = f"Watcher {watcher_name!r} key 'diff': must be a mapping"
        raise ConfigError(msg)
    if "type" not in config:
        msg = f"Watcher {watcher_name!r} key 'diff': missing required key 'type'"
        raise ConfigError(msg)
    plugin_type = config["type"]
    if not isinstance(plugin_type, str):
        msg = f"Watcher {watcher_name!r} key 'diff': 'type' must be a string"
        raise ConfigError(msg)
    params = {k: v for k, v in config.items() if k != "type"}
    try:
        return create_differ(plugin_type, **params)
    except KeyError as err:
        msg = f"Watcher {watcher_name!r} key 'diff': unknown differ plugin {plugin_type!r}"
        raise ConfigError(msg) from err
    except (TypeError, ValueError) as err:
        msg = f"Watcher {watcher_name!r} key 'diff': {err}"
        raise ConfigError(msg) from err


def _build_notifier(watcher_name: str, config: Any) -> Notifier:
    """Instantiate a Notifier from its configuration mapping.

    Args:
        watcher_name: Name of the watcher for error messages.
        config: Notifier configuration mapping.

    Returns:
        The instantiated Notifier.

    Raises:
        ConfigError: If configuration is invalid or names an unknown plugin.
    """
    if not isinstance(config, dict):
        msg = f"Watcher {watcher_name!r} key 'notify': entry must be a mapping"
        raise ConfigError(msg)
    if "type" not in config:
        msg = f"Watcher {watcher_name!r} key 'notify': entry missing required key 'type'"
        raise ConfigError(msg)
    plugin_type = config["type"]
    if not isinstance(plugin_type, str):
        msg = f"Watcher {watcher_name!r} key 'notify': 'type' must be a string"
        raise ConfigError(msg)
    params = {k: v for k, v in config.items() if k != "type"}
    try:
        return create_notifier(plugin_type, **params)
    except KeyError as err:
        msg = f"Watcher {watcher_name!r} key 'notify': unknown notifier plugin {plugin_type!r}"
        raise ConfigError(msg) from err
    except (TypeError, ValueError) as err:
        msg = f"Watcher {watcher_name!r} key 'notify': {err}"
        raise ConfigError(msg) from err


def _build_filter(watcher_name: str, entry: Any) -> Filter:
    """Instantiate a Filter from a config filter entry.

    Args:
        watcher_name: Name of the watcher for error messages.
        entry: Filter specification, either a string or a single-key mapping.

    Returns:
        The instantiated Filter.

    Raises:
        ConfigError: If the entry format is invalid or references an unknown plugin.
    """
    if isinstance(entry, str):
        try:
            return create_filter(entry)
        except KeyError as err:
            msg = f"Watcher {watcher_name!r} key 'filters': unknown filter {entry!r}"
            raise ConfigError(msg) from err
        except (TypeError, ValueError) as err:
            msg = f"Watcher {watcher_name!r} key 'filters': filter {entry!r} {err}"
            raise ConfigError(msg) from err

    if isinstance(entry, dict):
        if len(entry) != 1:
            keys_str = ", ".join(repr(k) for k in entry)
            msg = (
                f"Watcher {watcher_name!r} key 'filters': "
                f"filter entry must have exactly one key, got {keys_str}"
            )
            raise ConfigError(msg)
        filter_name, val = next(iter(entry.items()))
        if not isinstance(filter_name, str):
            msg = f"Watcher {watcher_name!r} key 'filters': filter name must be a string"
            raise ConfigError(msg)

        if filter_name in ("all", "any"):
            if not isinstance(val, list):
                msg = (
                    f"Watcher {watcher_name!r} key 'filters': "
                    f"{filter_name!r} requires a list of filters"
                )
                raise ConfigError(msg)
            if len(val) == 0:
                msg = (
                    f"Watcher {watcher_name!r} key 'filters': "
                    f"{filter_name!r} requires at least one filter"
                )
                raise ConfigError(msg)
            inner_filters = [_build_filter(watcher_name, item) for item in val]
            try:
                return create_filter(filter_name, *inner_filters)
            except (KeyError, TypeError, ValueError) as err:
                msg = f"Watcher {watcher_name!r} key 'filters': {err}"
                raise ConfigError(msg) from err

        if filter_name == "not":
            if isinstance(val, list) and len(val) != 1:
                msg = f"Watcher {watcher_name!r} key 'filters': 'not' requires exactly one filter"
                raise ConfigError(msg)
            inner_item = val[0] if isinstance(val, list) else val
            inner_filter = _build_filter(watcher_name, inner_item)
            try:
                return create_filter("not", inner_filter)
            except (KeyError, TypeError, ValueError) as err:
                msg = f"Watcher {watcher_name!r} key 'filters': {err}"
                raise ConfigError(msg) from err

        try:
            return create_filter(filter_name, val)
        except KeyError as err:
            msg = f"Watcher {watcher_name!r} key 'filters': unknown filter {filter_name!r}"
            raise ConfigError(msg) from err
        except (TypeError, ValueError) as err:
            msg = f"Watcher {watcher_name!r} key 'filters': filter {filter_name!r} {err}"
            raise ConfigError(msg) from err

    msg = (
        f"Watcher {watcher_name!r} key 'filters': "
        f"filter entry must be a name or mapping, got {entry!r}"
    )
    raise ConfigError(msg)


def _build_watcher(entry: Any, seen_names: set[str]) -> WatcherBuilder:
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

    for key in entry:
        if key not in _ALLOWED_WATCHER_KEYS:
            msg = f"Watcher {name!r} has unknown key {key!r}"
            raise ConfigError(msg)

    if "source" not in entry:
        msg = f"Watcher {name!r} missing required key 'source'"
        raise ConfigError(msg)
    source_obj = _build_source(name, entry["source"])

    if "diff" not in entry:
        msg = f"Watcher {name!r} missing required key 'diff'"
        raise ConfigError(msg)
    differ_obj = _build_differ(name, entry["diff"])

    builder = WatcherBuilder(name).source(source_obj).diff(differ_obj)

    if "interval" in entry:
        raw_interval = entry["interval"]
        if not isinstance(raw_interval, str):
            msg = f"Watcher {name!r} key 'interval': expected text, got {raw_interval!r}"
            raise ConfigError(msg)
        try:
            parsed_interval = parse_interval(raw_interval)
        except ConfigError as err:
            msg = f"Watcher {name!r} key 'interval': {err}"
            raise ConfigError(msg) from err
        builder.every(parsed_interval)

    if "filters" in entry:
        raw_filters = entry["filters"]
        if not isinstance(raw_filters, list):
            msg = f"Watcher {name!r} key 'filters': must be a list"
            raise ConfigError(msg)
        for filter_entry in raw_filters:
            builder.only_if(_build_filter(name, filter_entry))

    if "notify" in entry:
        raw_notify = entry["notify"]
        if not isinstance(raw_notify, list):
            msg = f"Watcher {name!r} key 'notify': must be a list"
            raise ConfigError(msg)
        for notifier_conf in raw_notify:
            builder.notify(_build_notifier(name, notifier_conf))

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
    data = _read_yaml(path)
    for key in data:
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            msg = f"Config file has unknown key {key!r}"
            raise ConfigError(msg)

    database = _resolve_database(data, path.parent)
    if "watchers" not in data:
        msg = f"Config file {path} lacks required key 'watchers'"
        raise ConfigError(msg)
    watchers_raw = data["watchers"]
    if not isinstance(watchers_raw, list):
        msg = f"Config file {path} key 'watchers' must be a list"
        raise ConfigError(msg)

    seen_names: set[str] = set()
    builders = [_build_watcher(entry, seen_names) for entry in watchers_raw]

    return Config(database=database, watchers=tuple(builders))
