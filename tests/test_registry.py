"""Tests for the plugin registry."""

from __future__ import annotations

from collections.abc import Iterable
from typing import (
    Annotated,
    Any,
    ClassVar,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    cast,
    runtime_checkable,
)

import pytest

from watchtower import (
    ChangeEvent,
    create,
    create_differ,
    create_filter,
    create_notifier,
    create_source,
    list_plugins,
    register_differ,
    register_filter,
    register_notifier,
    register_source,
)
from watchtower._models import Change, Item, Snapshot
from watchtower._registry import (
    _base_class_for,
    _is_checkable,
    _is_protocol_subclass,
    _Kind,
    _matches,
    _strip_annotated,
    _validate_init_args,
)
from watchtower.diffs import ItemDiff, TextDiff
from watchtower.diffs._base import Differ
from watchtower.filters import (
    KindIs,
    Matches,
    NewItems,
    PriceAbove,
    PriceBelow,
    TextContains,
)
from watchtower.filters._base import Filter
from watchtower.notifiers import (
    ConsoleNotifier,
    DesktopNotifier,
    DiscordNotifier,
)
from watchtower.notifiers._base import Notifier
from watchtower.sources import (
    FakeSource,
    FileSource,
    JSONAPISource,
    RSSSource,
    WebPageSource,
)
from watchtower.sources._base import Source


class _FakeBackend:
    """Minimal runtime-checkable ``_NotificationBackend`` stand-in for tests."""

    def send(self, title: str, message: str) -> str:
        return "id"


@pytest.mark.parametrize(
    ("kind", "name", "params", "expected"),
    [
        ("source", "fake", {"contents": ["step 1"]}, FakeSource),
        ("source", "rss", {"url": "http://test/feed"}, RSSSource),
        (
            "source",
            "webpage",
            {"url": "http://test/page", "selector": ".offer"},
            WebPageSource,
        ),
        ("source", "file", {"path": "/tmp/watchtower-test"}, FileSource),
        ("source", "json_api", {"url": "http://test/api"}, JSONAPISource),
        ("differ", "items", {}, ItemDiff),
        ("differ", "text", {"context_lines": 5}, TextDiff),
        ("filter", "new_items", {}, NewItems),
        ("filter", "kind_is", {"kind": "new"}, KindIs),
        ("filter", "price_below", {"limit": 3000}, PriceBelow),
        ("filter", "price_above", {"limit": 3000}, PriceAbove),
        ("filter", "text_contains", {"phrase": "agency"}, TextContains),
        ("filter", "matches", {"pattern": "foo"}, Matches),
        ("notifier", "console", {}, ConsoleNotifier),
        (
            "notifier",
            "discord",
            {"webhook_url": "http://example.com/hook"},
            DiscordNotifier,
        ),
        ("notifier", "desktop", {"backend": _FakeBackend()}, DesktopNotifier),
    ],
)
def test_all_builtin_plugins_are_registered(kind, name, params, expected) -> None:
    """Every built-in plugin can be constructed through the registry."""
    instance = create(kind, name, **params)
    assert isinstance(instance, expected)


def test_registry_registration_and_creation() -> None:
    """Test registering classes with decorators and creating instances with parameters."""

    @register_source("dummy_src")
    class DummySource(Source):
        def __init__(self, greeting: str) -> None:
            self.greeting = greeting

        def fetch(self) -> str:
            return ""

        def parse(self, raw: str) -> Iterable[Item]:
            return ()

    @register_differ("dummy_diff")
    class DummyDiffer(Differ):
        def __init__(self, mode: str = "fast") -> None:
            self.mode = mode

        def diff(self, old: Snapshot | None, new: Snapshot) -> list[Change]:
            return []

    @register_filter("dummy_filt")
    class DummyFilter(Filter):
        def matches(self, change: Change) -> bool:
            return True

    @register_notifier("dummy_notify")
    class DummyNotifier(Notifier):
        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint

        def send(self, event: ChangeEvent) -> None:
            pass

    src = create("source", "dummy_src", greeting="hello")
    assert isinstance(src, DummySource)
    assert src.greeting == "hello"

    diff = create("differ", "dummy_diff")
    assert isinstance(diff, DummyDiffer)
    assert diff.mode == "fast"

    plugins = list_plugins()
    assert "dummy_src" in plugins["source"]
    assert "dummy_diff" in plugins["differ"]
    assert "dummy_filt" in plugins["filter"]
    assert "dummy_notify" in plugins["notifier"]


def test_registry_unknown_kind_and_name_errors() -> None:
    """Test that requesting nonexistent kinds or plugins raises KeyError."""
    with pytest.raises(KeyError, match="Unknown plugin kind"):
        create("unknown_kind", "anything")

    with pytest.raises(KeyError, match="Unknown source plugin"):
        create("source", "nonexistent_source")


def test_create_kind_and_name_are_positional_only() -> None:
    """``kind``/``name`` are positional-only so ``kind`` constructor params pass through."""
    filt = create("filter", "kind_is", kind="new")
    assert isinstance(filt, KindIs)


def test_typed_factory_create_source() -> None:
    """Test create_source returns a properly typed Source instance."""
    source = create_source("fake", contents=["step 1"])
    assert isinstance(source, FakeSource)


def test_typed_factory_create_differ() -> None:
    """Test create_differ returns a properly typed Differ instance."""
    differ = create_differ("text", context_lines=5)
    assert isinstance(differ, TextDiff)


def test_typed_factory_create_notifier() -> None:
    """Test create_notifier returns a properly typed Notifier instance."""
    notifier = create_notifier("console")
    assert isinstance(notifier, ConsoleNotifier)


def test_registry_duplicate_name_raises() -> None:
    """Registering the same name twice for a kind raises ValueError."""

    @register_source("dup_src")
    class DupSource(Source):
        def fetch(self) -> str:
            return ""

        def parse(self, raw: str) -> Iterable[Item]:
            return ()

    with pytest.raises(ValueError, match="already registered"):

        @register_source("dup_src")
        class DupSourceAgain(Source):
            def fetch(self) -> str:
                return ""

            def parse(self, raw: str) -> Iterable[Item]:
                return ()


def test_registry_wrong_kind_class_raises() -> None:
    """Registering a class that is not a Source subclass raises TypeError."""
    with pytest.raises(TypeError, match="not a subclass of Source"):

        @register_source("not_a_source")
        class NotASource:
            def __init__(self) -> None:
                pass


def test_registry_wrong_argument_type_raises() -> None:
    """Passing an argument of the wrong type raises TypeError."""

    @register_source("bad_arg_src")
    class BadArgSource(Source):
        def __init__(self, count: int) -> None:
            self.count = count

        def fetch(self) -> str:
            return ""

        def parse(self, raw: str) -> Iterable[Item]:
            return ()

    with pytest.raises(TypeError, match="count"):
        create_source("bad_arg_src", count="not-an-int")


def test_registry_wrong_arity_raises() -> None:
    """Missing a required argument or passing an unexpected one raises TypeError."""

    @register_source("arity_src")
    class AritySource(Source):
        def __init__(self, required: str) -> None:
            self.required = required

        def fetch(self) -> str:
            return ""

        def parse(self, raw: str) -> Iterable[Item]:
            return ()

    with pytest.raises(TypeError, match="required"):
        create_source("arity_src")

    with pytest.raises(TypeError, match="unexpected"):
        create_source("arity_src", required="x", extra=1)


def test_filter_positional_argument_still_works() -> None:
    """Positional filter arguments (price_below: 3000) still construct correctly."""

    @register_filter("pos_filt")
    class PosFilter(Filter):
        def __init__(self, limit: float) -> None:
            self.limit = limit

        def matches(self, change: Change) -> bool:
            return True

    filt = create_filter("pos_filt", 3000)
    assert isinstance(filt, PosFilter)
    assert filt.limit == 3000


def test_desktop_notifier_accepts_runtime_checkable_backend() -> None:
    """A runtime-checkable Protocol backend passes argument validation."""

    class FakeBackend:
        def send(self, title: str, message: str) -> str:
            return "id"

    notifier = create_notifier("desktop", backend=FakeBackend())
    assert isinstance(notifier, DesktopNotifier)


def test_base_class_for_unknown_kind_raises() -> None:
    """An invalid kind raises ValueError even though it's unreachable via the Literal."""
    with pytest.raises(ValueError, match="Unknown plugin kind"):
        _base_class_for(cast(_Kind, "bogus"))


def test_strip_annotated_unwraps_annotated() -> None:
    """_strip_annotated returns the underlying type of Annotated."""
    assert _strip_annotated(Annotated[int, "metadata"]) is int


def test_is_checkable_any_is_false() -> None:
    """Any is not checkable with isinstance."""
    assert _is_checkable(Any) is False


def test_is_checkable_protocol_subclass_without_runtime_checkable() -> None:
    """A Protocol without @runtime_checkable is not checkable."""

    class _Proto(Protocol):
        def method(self) -> int: ...

    assert _is_protocol_subclass(_Proto) is True
    assert _is_checkable(_Proto) is False


def test_is_checkable_runtime_checkable_protocol() -> None:
    """A @runtime_checkable Protocol is checkable."""

    @runtime_checkable
    class _Proto(Protocol):
        def method(self) -> int: ...

    assert _is_protocol_subclass(_Proto) is True
    assert _is_checkable(_Proto) is True


def test_is_checkable_protocol_itself_is_not_a_subclass() -> None:
    """Protocol itself is not treated as a Protocol subclass."""
    assert _is_protocol_subclass(Protocol) is False


def test_is_checkable_generic_protocol() -> None:
    """Generic parameterized Protocols are checkable only when @runtime_checkable."""
    T = TypeVar("T")

    class _GenNonRt(Protocol, Generic[T]):
        def method(self) -> T: ...

    @runtime_checkable
    class _GenRt(Protocol, Generic[T]):
        def method(self) -> T: ...

    assert _is_checkable(_GenNonRt[int]) is False
    assert _is_checkable(_GenRt[int]) is True


def test_matches_runtime_checkable_protocol() -> None:
    """A @runtime_checkable Protocol accepts conforming values and rejects others."""

    @runtime_checkable
    class _Proto(Protocol):
        def method(self) -> int: ...

    class _Impl:
        def method(self) -> int:
            return 1

    assert _matches(_Impl(), _Proto) is True
    assert _matches(object(), _Proto) is False


def test_matches_non_checkable_protocol_returns_true() -> None:
    """A Protocol without @runtime_checkable makes isinstance raise TypeError -> True."""

    class _Proto(Protocol):
        def method(self) -> int: ...

    assert _matches(object(), _Proto) is True


def test_matches_generic_non_checkable_protocol_returns_true() -> None:
    """A generic Parameterized non-@runtime_checkable Protocol is skipped."""
    T = TypeVar("T")

    class _GenProto(Protocol, Generic[T]):
        def method(self) -> T: ...

    assert _matches(object(), _GenProto[int]) is True


def test_validate_init_args_signature_error() -> None:
    """A class whose __init__ has no inspectable signature is skipped."""

    class _NoSignature:
        __init__ = int  # type: ignore[method-assign]

    _validate_init_args(_NoSignature)


def test_validate_init_args_get_type_hints_error() -> None:
    """A class with an unresolvable annotation is skipped."""

    class _Unresolvable:
        def __init__(self, value: NotDefinedAnywhere) -> None:  # noqa: F821
            self.value = value

    _validate_init_args(_Unresolvable, "anything")


def test_validate_init_args_var_positional_error() -> None:
    """Invalid element in *args: T raises TypeError."""

    class _VarPos:
        def __init__(self, *items: int) -> None:
            self.items = items

    with pytest.raises(TypeError, match="items"):
        _validate_init_args(_VarPos, 1, 2, "not-an-int")


def test_validate_init_args_var_keyword_error() -> None:
    """Invalid value in **kwargs: T raises TypeError."""

    class _VarKw:
        def __init__(self, **values: int) -> None:
            self.values = values

    with pytest.raises(TypeError, match="values"):
        _validate_init_args(_VarKw, a=1, b="not-an-int")


def test_list_plugins_unknown_kind() -> None:
    """An unknown kind returns an empty list for that kind."""
    assert list_plugins("bogus") == {"bogus": []}


def test_matches_literal_annotation_returns_true() -> None:
    """Exotic annotations (Literal, ClassVar, ...) that can't be checked are skipped."""
    assert _matches("anything", Literal["a", "b"]) is True
    assert _matches(42, Literal["a", "b"]) is True


def test_matches_forward_ref_annotation_returns_true() -> None:
    """String forward references have no origin and can't be checked."""
    assert _matches("anything", "SomeUndefinedClass") is True


def test_is_checkable_forward_ref_annotation_is_false() -> None:
    """A string forward reference is not a type, so it is not checkable."""
    assert _is_checkable("SomeUndefinedClass") is False


def test_is_checkable_exotic_generic_alias_is_false() -> None:
    """A generic alias whose origin is not a type is not checkable."""
    # ClassVar[int] has origin ClassVar, which is a _SpecialForm, not a type.
    assert _is_checkable(ClassVar[int]) is False
