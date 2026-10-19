"""Extensible plugin registry for sources, differs, filters, and notifiers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

# Internal registry mapping plugin kind (e.g. 'source', 'differ') to dict of name -> factory/class
_REGISTRY: dict[str, dict[str, type[Any]]] = {
    "source": {},
    "differ": {},
    "filter": {},
    "notifier": {},
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
        if kind not in _REGISTRY:
            _REGISTRY[kind] = {}
        _REGISTRY[kind][name] = cls
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


def create(kind: str, name: str, **params: Any) -> Any:
    """Instantiate a registered plugin class with provided keyword arguments.

    Args:
        kind: Category of the plugin ('source', 'differ', 'filter', 'notifier').
        name: Registered name of the plugin.
        **params: Arguments passed to the plugin constructor.

    Returns:
        An instance of the registered plugin class.

    Raises:
        KeyError: If the category or plugin name is not registered.
    """
    if kind not in _REGISTRY:
        valid_kinds = ", ".join(repr(k) for k in _REGISTRY)
        msg = f"Unknown plugin kind {kind!r}. Valid kinds are: {valid_kinds}"
        raise KeyError(msg)

    plugins = _REGISTRY[kind]
    if name not in plugins:
        available = ", ".join(repr(p) for p in plugins)
        msg = f"Unknown {kind} plugin {name!r}. Available plugins: {available}"
        raise KeyError(msg)

    cls = plugins[name]
    return cls(**params)


def list_plugins(kind: str | None = None) -> dict[str, list[str]]:
    """List registered plugins grouped by category.

    Args:
        kind: Optional category to filter by ('source', 'differ', etc.).

    Returns:
        Dictionary mapping plugin categories to lists of registered plugin names.
    """
    if kind is not None:
        if kind not in _REGISTRY:
            return {kind: []}
        return {kind: sorted(_REGISTRY[kind].keys())}
    return {k: sorted(v.keys()) for k, v in _REGISTRY.items()}
