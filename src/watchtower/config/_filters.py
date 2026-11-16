"""Building Filter instances from configuration specifications."""

from __future__ import annotations

from watchtower._errors import ConfigError
from watchtower._registry import create_filter, list_plugins
from watchtower.filters._base import Filter

type _RawFilter = dict[object, object]
type _ParsedFilter = tuple[str, object]


def _create_filter(watcher_name: str, name: str, *args: object) -> Filter:
    """Create a registered filter, turning a bad name or bad arguments into ConfigError."""
    registered = list_plugins("filter").get("filter", [])
    if name not in registered:
        msg = f"Watcher {watcher_name!r} key 'filters': unknown filter {name!r}"
        raise ConfigError(msg)
    try:
        return create_filter(name, *args)
    except (TypeError, ValueError) as err:
        msg = f"Watcher {watcher_name!r} key 'filters': filter {name!r} {err}"
        raise ConfigError(msg) from err


def _extract_filter_entry(watcher_name: str, raw_filter: _RawFilter) -> _ParsedFilter:
    """Validate single-key filter mapping and extract its name and argument."""
    if len(raw_filter) != 1:
        keys_str = ", ".join(repr(k) for k in raw_filter)
        msg = (
            f"Watcher {watcher_name!r} key 'filters': "
            f"filter entry must have exactly one key, got {keys_str}"
        )
        raise ConfigError(msg)
    filter_name, argument = next(iter(raw_filter.items()))
    if not isinstance(filter_name, str):
        msg = f"Watcher {watcher_name!r} key 'filters': filter name must be a string"
        raise ConfigError(msg)
    return filter_name, argument


def _build_n_ary_filter(watcher_name: str, name: str, argument: object) -> Filter:
    """Build an 'all' or 'any' composite filter from its item list."""
    if not isinstance(argument, list):
        msg = f"Watcher {watcher_name!r} key 'filters': {name!r} requires a list of filters"
        raise ConfigError(msg)
    if len(argument) == 0:
        msg = f"Watcher {watcher_name!r} key 'filters': {name!r} requires at least one filter"
        raise ConfigError(msg)
    inner_filters = [build_filter(watcher_name, item) for item in argument]
    return _create_filter(watcher_name, name, *inner_filters)


def _build_not_filter(watcher_name: str, argument: object) -> Filter:
    """Build a 'not' composite filter from its single target filter."""
    if isinstance(argument, list) and len(argument) != 1:
        msg = f"Watcher {watcher_name!r} key 'filters': 'not' requires exactly one filter"
        raise ConfigError(msg)
    inner_item = argument[0] if isinstance(argument, list) else argument
    inner_filter = build_filter(watcher_name, inner_item)
    return _create_filter(watcher_name, "not", inner_filter)


def build_filter(watcher_name: str, raw_filter: object) -> Filter:
    """Instantiate a Filter from a config filter entry.

    Args:
        watcher_name: Name of the watcher for error messages.
        raw_filter: Filter specification, either a string or a single-key mapping.

    Returns:
        The instantiated Filter.

    Raises:
        ConfigError: If the entry format is invalid or references an unknown plugin.
    """
    if isinstance(raw_filter, str):
        return _create_filter(watcher_name, raw_filter)

    if not isinstance(raw_filter, dict):
        msg = (
            f"Watcher {watcher_name!r} key 'filters': "
            f"filter entry must be a name or mapping, got {raw_filter!r}"
        )
        raise ConfigError(msg)

    filter_name, argument = _extract_filter_entry(watcher_name, raw_filter)

    if filter_name in ("all", "any"):
        return _build_n_ary_filter(watcher_name, filter_name, argument)

    if filter_name == "not":
        return _build_not_filter(watcher_name, argument)

    return _create_filter(watcher_name, filter_name, argument)
