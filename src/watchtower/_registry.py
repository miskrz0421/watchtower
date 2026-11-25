"""Extensible plugin registry for sources, differs, filters, and notifiers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast, get_args, get_type_hints

if TYPE_CHECKING:
    from watchtower.diffs._base import Differ
    from watchtower.filters._base import Filter
    from watchtower.notifiers._base import Notifier
    from watchtower.sources._base import Source

_T = TypeVar("_T")

type _Kind = Literal["source", "differ", "filter", "notifier"]

# Every plugin class has its own constructor, known only at runtime (ADR-034).
type _PluginArg = Any

# Types a config value can have; arguments of other types are not checked.
_SIMPLE_TYPES = frozenset({str, int, float, bool, NoneType, Path})
_VARIADIC_KINDS = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)

# Per-kind registries storing plugin classes keyed by name.
_SOURCES: dict[str, type[Source]] = {}
_DIFFERS: dict[str, type[Differ]] = {}
_FILTERS: dict[str, type[Filter]] = {}
_NOTIFIERS: dict[str, type[Notifier]] = {}

# Unified view used only by list_plugins() for convenience.
_ALL_REGISTRIES: dict[str, dict[str, type[object]]] = {
    "source": cast(dict[str, type[object]], _SOURCES),
    "differ": cast(dict[str, type[object]], _DIFFERS),
    "filter": cast(dict[str, type[object]], _FILTERS),
    "notifier": cast(dict[str, type[object]], _NOTIFIERS),
}


def _base_class_for(kind: _Kind) -> type[object]:
    """Return the abstract base class plugins of ``kind`` must subclass.

    The import is lazy (inside the function) so that importing this module never
    triggers imports of the plugin packages, avoiding circular imports.

    Args:
        kind: The plugin category.

    Returns:
        The abstract base class of the category.

    Raises:
        ValueError: If the category is unknown.
    """
    match kind:
        case "source":
            from watchtower.sources._base import Source

            return Source
        case "differ":
            from watchtower.diffs._base import Differ

            return Differ
        case "filter":
            from watchtower.filters._base import Filter

            return Filter
        case "notifier":
            from watchtower.notifiers._base import Notifier

            return Notifier
    # Unreachable: ``kind`` is a Literal, but keep the function total.
    raise ValueError(f"Unknown plugin kind {kind!r}")


def _register(kind: _Kind, name: str) -> Callable[[type[_T]], type[_T]]:
    """Internal decorator helper to register a plugin class under a specific kind.

    Args:
        kind: The plugin category ('source', 'differ', 'filter', or 'notifier').
        name: The unique identifier for this plugin within its category.

    Returns:
        Decorator function that registers the class and returns it unchanged.

    Raises:
        TypeError: If the class is not a subclass of the base class for ``kind``.
        ValueError: If ``name`` is already registered for ``kind``.
    """

    def decorator(cls: type[_T]) -> type[_T]:
        """Register the class and return it unchanged.

        Args:
            cls: Plugin class to register.

        Returns:
            The same class.

        Raises:
            TypeError: If the class is not a subclass of the base class for ``kind``.
            ValueError: If ``name`` is already registered for ``kind``.
        """
        base = _base_class_for(kind)
        if not isinstance(cls, type) or not issubclass(cls, base):
            msg = (
                f"{cls!r} is not a subclass of {base.__name__}; "
                f"cannot register it as {kind} plugin {name!r}"
            )
            raise TypeError(msg)
        target = _ALL_REGISTRIES[kind]
        if name in target:
            msg = f"{kind} plugin {name!r} is already registered"
            raise ValueError(msg)
        target[name] = cls
        return cls

    return decorator


def register_source(name: str) -> Callable[[type[_T]], type[_T]]:
    """Decorator to register a Source implementation.

    Args:
        name: Unique name for the source plugin.

    Returns:
        Decorator that registers the class and returns it unchanged.
    """
    return _register("source", name)


def register_differ(name: str) -> Callable[[type[_T]], type[_T]]:
    """Decorator to register a Differ implementation.

    Args:
        name: Unique name for the differ plugin.

    Returns:
        Decorator that registers the class and returns it unchanged.
    """
    return _register("differ", name)


def register_filter(name: str) -> Callable[[type[_T]], type[_T]]:
    """Decorator to register a Filter implementation.

    Args:
        name: Unique name for the filter plugin.

    Returns:
        Decorator that registers the class and returns it unchanged.
    """
    return _register("filter", name)


def register_notifier(name: str) -> Callable[[type[_T]], type[_T]]:
    """Decorator to register a Notifier implementation.

    Args:
        name: Unique name for the notifier plugin.

    Returns:
        Decorator that registers the class and returns it unchanged.
    """
    return _register("notifier", name)


def _lookup[T](registry: dict[str, type[T]], kind: str, name: str) -> type[T]:
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


def _accepts(annotation: type | UnionType, value: object) -> bool:
    """Return whether a constructor argument fits a simple annotation.

    Args:
        annotation: Resolved annotation of the constructor parameter.
        value: Argument passed for the parameter.

    Returns:
        True if the value fits, or if the annotation has a type that is not simple.
    """
    options = get_args(annotation) if isinstance(annotation, UnionType) else (annotation,)
    if not _SIMPLE_TYPES.issuperset(options):
        return True
    if isinstance(value, bool):
        return bool in options
    if isinstance(value, int) and float in options:
        return True
    return isinstance(value, annotation)


def _check_arguments(cls: type[object], *args: object, **params: object) -> None:
    """Check arguments against the signature and simple annotations of a constructor.

    Args:
        cls: Plugin class to be created.
        *args: Positional constructor arguments.
        **params: Keyword constructor arguments.

    Raises:
        TypeError: If an argument is missing, unexpected or of the wrong type.
    """
    signature = inspect.signature(cls)
    bound = signature.bind(*args, **params)
    try:
        hints = get_type_hints(cls.__init__)
    except NameError:
        # An annotation is imported only for type checkers, so it cannot be resolved.
        return
    for name, value in bound.arguments.items():
        if name not in hints or signature.parameters[name].kind in _VARIADIC_KINDS:
            continue
        if not _accepts(hints[name], value):
            expected = inspect.formatannotation(hints[name])
            # The value itself may be a secret, so only its type is shown.
            msg = f"argument {name!r} must be {expected}, got {type(value).__name__}"
            raise TypeError(msg)


def create_source(name: str, **params: _PluginArg) -> Source:
    """Instantiate a registered Source plugin.

    Args:
        name: Registered name of the source plugin.
        **params: Arguments passed to the source constructor.

    Returns:
        An instance of the registered Source subclass.

    Raises:
        KeyError: If the source plugin name is not registered.
        TypeError: If the arguments do not match the source constructor.
    """
    cls = _lookup(_SOURCES, "source", name)
    _check_arguments(cls, **params)
    return cls(**params)


def create_differ(name: str, **params: _PluginArg) -> Differ:
    """Instantiate a registered Differ plugin.

    Args:
        name: Registered name of the differ plugin.
        **params: Arguments passed to the differ constructor.

    Returns:
        An instance of the registered Differ subclass.

    Raises:
        KeyError: If the differ plugin name is not registered.
        TypeError: If the arguments do not match the differ constructor.
    """
    cls = _lookup(_DIFFERS, "differ", name)
    _check_arguments(cls, **params)
    return cls(**params)


def create_filter(name: str, *args: _PluginArg, **params: _PluginArg) -> Filter:
    """Instantiate a registered Filter plugin.

    Args:
        name: Registered name of the filter plugin.
        *args: Positional arguments passed to the filter constructor, so the
            config can say ``price_below: 3000`` without naming the parameter.
        **params: Keyword arguments passed to the filter constructor.

    Returns:
        An instance of the registered Filter subclass.

    Raises:
        KeyError: If the filter plugin name is not registered.
        TypeError: If the arguments do not match the filter constructor.
    """
    cls = _lookup(_FILTERS, "filter", name)
    _check_arguments(cls, *args, **params)
    return cls(*args, **params)


def create_notifier(name: str, **params: _PluginArg) -> Notifier:
    """Instantiate a registered Notifier plugin.

    Args:
        name: Registered name of the notifier plugin.
        **params: Arguments passed to the notifier constructor.

    Returns:
        An instance of the registered Notifier subclass.

    Raises:
        KeyError: If the notifier plugin name is not registered.
        TypeError: If the arguments do not match the notifier constructor.
    """
    cls = _lookup(_NOTIFIERS, "notifier", name)
    _check_arguments(cls, **params)
    return cls(**params)


def create(kind: str, name: str, /, **params: _PluginArg) -> Source | Differ | Filter | Notifier:
    """Instantiate a registered plugin class with provided keyword arguments.

    Prefer the type-safe alternatives: ``create_source``, ``create_differ``,
    ``create_filter``, or ``create_notifier``.

    Args:
        kind: Category of the plugin ('source', 'differ', 'filter', 'notifier').
            Positional-only, so that a constructor parameter named e.g. ``kind``
            (such as ``KindIs``'s) can be passed through ``**params``.
        name: Registered name of the plugin. Positional-only for the same reason.
        **params: Arguments passed to the plugin constructor.

    Returns:
        An instance of the registered plugin class.

    Raises:
        KeyError: If the category or plugin name is not registered.
        TypeError: If the arguments do not match the plugin constructor.
    """
    factories: dict[str, Callable[..., Source | Differ | Filter | Notifier]] = {
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
