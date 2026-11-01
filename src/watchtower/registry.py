"""Extensible plugin registry for sources, differs, filters, and notifiers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from watchtower.diffs.base import Differ
    from watchtower.notifiers.base import Notifier
    from watchtower.sources.base import Source

T = TypeVar("T")

# Per-kind registries storing plugin classes keyed by name.
# Runtime values are plain ``type[object]``; the typed factory functions
# below provide the narrowed return types via TYPE_CHECKING imports.
_SOURCES: dict[str, type[object]] = {}
_DIFFERS: dict[str, type[object]] = {}
_FILTERS: dict[str, type[object]] = {}
_NOTIFIERS: dict[str, type[object]] = {}

# Unified view used only by list_plugins() for convenience.
_ALL_REGISTRIES: dict[str, dict[str, type[object]]] = {
    "source": _SOURCES,
    "differ": _DIFFERS,
    "filter": _FILTERS,
    "notifier": _NOTIFIERS,
}


def _register(kind: str, name: str) -> Callable[[type[T]], type[T]]:
    """Internal decorator helper to register a plugin class under a specific kind.

    Args:
        kind: The plugin category (e.g., 'source', 'differ', 'filter', 'notifier').
        name: The unique identifier for this plugin within its category.

    Returns:
        Decorator function that registers the class and returns it unchanged.
    """

    def decorator(cls: type[T]) -> type[T]:
        if kind not in _ALL_REGISTRIES:
            _ALL_REGISTRIES[kind] = {}
        _ALL_REGISTRIES[kind][name] = cls
        return cls

    return decorator


def register_source(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a Source implementation.

    Args:
        name: Unique name for the source plugin.
    """
    return _register("source", name)


def register_differ(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a Differ implementation.

    Args:
        name: Unique name for the differ plugin.
    """
    return _register("differ", name)


def register_filter(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a Filter implementation.

    Args:
        name: Unique name for the filter plugin.
    """
    return _register("filter", name)


def register_notifier(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a Notifier implementation.

    Args:
        name: Unique name for the notifier plugin.
    """
    return _register("notifier", name)


def _lookup(registry: dict[str, type[object]], kind: str, name: str) -> type[object]:
    """Look up a plugin class in a typed registry, raising KeyError if not found.

    Args:
        registry: The per-kind registry dictionary.
        kind: Category name (for error messages).
        name: Plugin name to look up.

    Returns:
        The registered plugin class.

    Raises:
        KeyError: If the plugin name is not registered.
    """
    if name not in registry:
        available = ", ".join(repr(p) for p in registry)
        msg = f"Unknown {kind} plugin {name!r}. Available plugins: {available}"
        raise KeyError(msg)
    return registry[name]


def create_source(name: str, **params: Any) -> Source:
    """Instantiate a registered Source plugin.

    Args:
        name: Registered name of the source plugin.
        **params: Arguments passed to the source constructor.

    Returns:
        An instance of the registered Source subclass.

    Raises:
        KeyError: If the source plugin name is not registered.
    """
    cls = _lookup(_SOURCES, "source", name)
    return cls(**params)  # type: ignore[return-value]


def create_differ(name: str, **params: Any) -> Differ:
    """Instantiate a registered Differ plugin.

    Args:
        name: Registered name of the differ plugin.
        **params: Arguments passed to the differ constructor.

    Returns:
        An instance of the registered Differ subclass.

    Raises:
        KeyError: If the differ plugin name is not registered.
    """
    cls = _lookup(_DIFFERS, "differ", name)
    return cls(**params)  # type: ignore[return-value]


def create_filter(name: str, **params: Any) -> object:
    """Instantiate a registered Filter plugin.

    Args:
        name: Registered name of the filter plugin.
        **params: Arguments passed to the filter constructor.

    Returns:
        An instance of the registered filter class.

    Raises:
        KeyError: If the filter plugin name is not registered.
    """
    cls = _lookup(_FILTERS, "filter", name)
    return cls(**params)


def create_notifier(name: str, **params: Any) -> Notifier:
    """Instantiate a registered Notifier plugin.

    Args:
        name: Registered name of the notifier plugin.
        **params: Arguments passed to the notifier constructor.

    Returns:
        An instance of the registered Notifier subclass.

    Raises:
        KeyError: If the notifier plugin name is not registered.
    """
    cls = _lookup(_NOTIFIERS, "notifier", name)
    return cls(**params)  # type: ignore[return-value]


def create(kind: str, name: str, **params: Any) -> Source | Differ | Notifier | object:
    """Instantiate a registered plugin class with provided keyword arguments.

    Prefer the type-safe alternatives: ``create_source``, ``create_differ``,
    ``create_filter``, or ``create_notifier``.

    Args:
        kind: Category of the plugin ('source', 'differ', 'filter', 'notifier').
        name: Registered name of the plugin.
        **params: Arguments passed to the plugin constructor.

    Returns:
        An instance of the registered plugin class.

    Raises:
        KeyError: If the category or plugin name is not registered.
    """
    factories: dict[str, Callable[..., Source | Differ | Notifier | object]] = {
        "source": create_source,
        "differ": create_differ,
        "filter": create_filter,
        "notifier": create_notifier,
    }
    if kind not in factories:
        valid_kinds = ", ".join(repr(k) for k in factories)
        msg = f"Unknown plugin kind {kind!r}. Valid kinds are: {valid_kinds}"
        raise KeyError(msg)
    return factories[kind](name, **params)


def list_plugins(kind: str | None = None) -> dict[str, list[str]]:
    """List registered plugins grouped by category.

    Args:
        kind: Optional category to filter by ('source', 'differ', etc.).

    Returns:
        Dictionary mapping plugin categories to lists of registered plugin names.
    """
    if kind is not None:
        if kind not in _ALL_REGISTRIES:
            return {kind: []}
        return {kind: sorted(_ALL_REGISTRIES[kind].keys())}
    return {k: sorted(v.keys()) for k, v in _ALL_REGISTRIES.items()}
