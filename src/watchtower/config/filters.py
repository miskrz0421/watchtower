"""Building Filter instances from configuration specifications."""

from __future__ import annotations

from typing import Any

from watchtower.errors import ConfigError
from watchtower.filters.base import Filter
from watchtower.registry import create_filter, list_plugins


def _safe_create_leaf_filter(watcher_name: str, name: str, *args: Any) -> Filter:
    """Instantiate a leaf filter plugin, mapping exceptions to ConfigError."""
    registered = list_plugins("filter").get("filter", [])
    if name not in registered:
        msg = f"Watcher {watcher_name!r} key 'filters': unknown filter {name!r}"
        raise ConfigError(msg)
    try:
        return create_filter(name, *args)
    except (TypeError, ValueError, KeyError) as err:
        msg = f"Watcher {watcher_name!r} key 'filters': filter {name!r} {err}"
        raise ConfigError(msg) from err


def _safe_create_composite_filter(watcher_name: str, name: str, *inner_filters: Filter) -> Filter:
    """Instantiate a composite filter plugin, mapping exceptions to ConfigError."""
    registered = list_plugins("filter").get("filter", [])
    if name not in registered:
        msg = f"Watcher {watcher_name!r} key 'filters': unknown filter {name!r}"
        raise ConfigError(msg)
    try:
        return create_filter(name, *inner_filters)
    except (TypeError, ValueError, KeyError) as err:
        msg = f"Watcher {watcher_name!r} key 'filters': {err}"
        raise ConfigError(msg) from err


def _extract_filter_entry(watcher_name: str, entry: dict[Any, Any]) -> tuple[str, Any]:
    """Validate single-key filter mapping and extract its name and value."""
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
    return filter_name, val


def _build_n_ary_filter(watcher_name: str, name: str, val: object) -> Filter:
    """Build an 'all' or 'any' composite filter from its item list."""
    if not isinstance(val, list):
        msg = f"Watcher {watcher_name!r} key 'filters': {name!r} requires a list of filters"
        raise ConfigError(msg)
    if len(val) == 0:
        msg = f"Watcher {watcher_name!r} key 'filters': {name!r} requires at least one filter"
        raise ConfigError(msg)
    inner_filters = [build_filter(watcher_name, item) for item in val]
    return _safe_create_composite_filter(watcher_name, name, *inner_filters)


def _build_not_filter(watcher_name: str, val: object) -> Filter:
    """Build a 'not' composite filter from its single target filter."""
    if isinstance(val, list) and len(val) != 1:
        msg = f"Watcher {watcher_name!r} key 'filters': 'not' requires exactly one filter"
        raise ConfigError(msg)
    inner_item = val[0] if isinstance(val, list) else val
    inner_filter = build_filter(watcher_name, inner_item)
    return _safe_create_composite_filter(watcher_name, "not", inner_filter)


def build_filter(watcher_name: str, entry: object) -> Filter:
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
        return _safe_create_leaf_filter(watcher_name, entry)

    if not isinstance(entry, dict):
        msg = (
            f"Watcher {watcher_name!r} key 'filters': "
            f"filter entry must be a name or mapping, got {entry!r}"
        )
        raise ConfigError(msg)

    filter_name, val = _extract_filter_entry(watcher_name, entry)

    if filter_name in ("all", "any"):
        return _build_n_ary_filter(watcher_name, filter_name, val)

    if filter_name == "not":
        return _build_not_filter(watcher_name, val)

    return _safe_create_leaf_filter(watcher_name, filter_name, val)
