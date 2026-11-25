"""Extensible plugin registry for sources, differs, filters, and notifiers."""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    Protocol,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

if TYPE_CHECKING:
    from watchtower.diffs._base import Differ
    from watchtower.filters._base import Filter
    from watchtower.notifiers._base import Notifier
    from watchtower.sources._base import Source

_T = TypeVar("_T")

type _Kind = Literal["source", "differ", "filter", "notifier"]

# Plugin constructor arguments cannot be statically narrowed: every plugin
# class has its own constructor signature, and the class is resolved by name
# at runtime. Arguments are validated against the resolved class's annotations
# at creation time, so ``Any`` is the correct (and only safe) static type here.
# Named for documentation clarity rather than for narrowing.
type _PluginArg = Any

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
        """Register the class and return it unchanged."""
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


def _strip_annotated(annotation: object) -> object:
    """Unwrap ``typing.Annotated`` to its underlying type."""
    if get_origin(annotation) is Annotated:
        return get_args(annotation)[0]
    return annotation


def _is_protocol_subclass(annotation: object) -> bool:
    """Return whether ``annotation`` is a ``Protocol`` subclass (not ``Protocol`` itself)."""
    if annotation is Protocol:
        return False
    if isinstance(annotation, type):
        try:
            return issubclass(annotation, Protocol)
        except TypeError:
            return False
    # GenericAlias (e.g. SomeProtocol[int]): check its origin.
    origin = get_origin(annotation)
    if origin is not None and isinstance(origin, type):
        try:
            return issubclass(origin, Protocol)
        except TypeError:
            return False
    return False


def _is_runtime_checkable_protocol(annotation: type) -> bool:
    """Return whether ``annotation`` is a ``@runtime_checkable`` Protocol."""
    return bool(getattr(annotation, "_is_runtime_protocol", False))


def _is_checkable(annotation: object) -> bool:
    """Return whether ``annotation`` can be validated with ``isinstance``.

    Plain classes (including ``NoneType``) and ``@runtime_checkable`` Protocols
    are checkable. ``Any``, non-``@runtime_checkable`` Protocols,
    ``typing.TextIO`` and similar are not, so callers that use them are skipped
    rather than rejected.
    """
    annotation = _strip_annotated(annotation)
    if annotation is Any:
        return False
    origin = get_origin(annotation)
    if origin is None:
        if not isinstance(annotation, type):
            return False
        # Protocol subclasses are only checkable when decorated with
        # @runtime_checkable; isinstance() raises TypeError otherwise.
        if _is_protocol_subclass(annotation):
            return _is_runtime_checkable_protocol(annotation)
        return True
    if origin is types.UnionType:
        return all(_is_checkable(arg) for arg in get_args(annotation))
    # Generic alias (list, Sequence, SomeProtocol[int], ...): check via origin.
    if isinstance(origin, type):
        return _is_checkable(origin)
    return False


def _matches(value: object, annotation: object) -> bool:
    """Return whether ``value`` satisfies ``annotation``."""
    annotation = _strip_annotated(annotation)

    # Numeric widening: accept ``int`` where ``float`` is expected. YAML parses
    # bare numbers as ``int`` (e.g. ``price_below: 2500``), and ``isinstance``
    # would otherwise reject a perfectly valid configuration value.
    if annotation is float and isinstance(value, int) and not isinstance(value, bool):
        return True

    if isinstance(annotation, type):
        try:
            return isinstance(value, annotation)
        except TypeError:
            # Not runtime-checkable (e.g. a Protocol without @runtime_checkable).
            return True

    origin = get_origin(annotation)
    if origin is None:
        return True

    if origin is types.UnionType:
        return any(_matches(value, arg) for arg in get_args(annotation))

    # Generic alias (list, Sequence, ...): validate the origin only.
    if isinstance(origin, type):
        try:
            return isinstance(value, origin)
        except TypeError:
            # Not runtime-checkable (e.g. a generic non-@runtime_checkable Protocol).
            return True

    return True


def _validate_init_args(cls: type[object], *args: object, **kwargs: object) -> None:
    """Validate constructor arguments against their type annotations.

    Positional and keyword arguments are bound to ``cls.__init__``'s signature
    (catching arity errors) and each value is checked against its annotation.
    Annotations that cannot be checked at runtime are skipped so that valid
    calls are never rejected with false positives.

    Args:
        cls: The class whose constructor is being called.
        *args: Positional arguments passed to the constructor.
        **kwargs: Keyword arguments passed to the constructor.

    Raises:
        TypeError: If the arguments do not match the constructor's signature
            or type annotations. The message names the class and the offending
            argument so callers (such as the config loader) can wrap it.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return

    # ``__init__``'s first parameter is the implicit instance (``self``); drop it
    # so we bind only the arguments the caller actually passes.
    parameters = list(sig.parameters.values())
    if parameters and parameters[0].name in ("self", "cls"):
        parameters = parameters[1:]
        sig = sig.replace(parameters=parameters)

    try:
        bound = sig.bind(*args, **kwargs)
    except TypeError as err:
        msg = f"{cls.__name__}(): {err}"
        raise TypeError(msg) from err

    bound.apply_defaults()
    try:
        hints = get_type_hints(cls.__init__)
    except Exception:
        hints = {}

    for param_name, value in bound.arguments.items():
        param = sig.parameters.get(param_name)
        expected = hints.get(param_name)
        if expected is None or not _is_checkable(expected):
            continue

        if param is not None and param.kind is inspect.Parameter.VAR_POSITIONAL:
            # *args: T  -> validate every element against T.
            for index, item in enumerate(value):
                if not _matches(item, expected):
                    msg = (
                        f"{cls.__name__}.__init__: argument {param_name!r}[{index}] must be "
                        f"{repr(expected)}, got {item!r}"
                    )
                    raise TypeError(msg)
        elif param is not None and param.kind is inspect.Parameter.VAR_KEYWORD:
            # **kwargs: T -> validate every value against T.
            for key, item in value.items():
                if not _matches(item, expected):
                    msg = (
                        f"{cls.__name__}.__init__: argument {param_name!r}[{key!r}] must be "
                        f"{repr(expected)}, got {item!r}"
                    )
                    raise TypeError(msg)
        else:
            if not _matches(value, expected):
                msg = (
                    f"{cls.__name__}.__init__: argument {param_name!r} must be "
                    f"{repr(expected)}, got {value!r}"
                )
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
    _validate_init_args(cls, **params)
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
    _validate_init_args(cls, **params)
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
    _validate_init_args(cls, *args, **params)
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
    _validate_init_args(cls, **params)
    return cls(**params)


def create(kind: str, name: str, /, **params: _PluginArg) -> Source | Differ | Filter | Notifier:
    """Instantiate a registered plugin class with provided keyword arguments.

    Prefer the type-safe alternatives: ``create_source``, ``create_differ``,
    ``create_filter``, or ``create_notifier``.

    Args:
        kind: Category of the plugin ('source', 'differ', 'filter', 'notifier').
            Positional-only, so that a constructor parameter named e.g.``kind``
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
