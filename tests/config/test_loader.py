"""Tests for loading watcher configuration from YAML."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from textwrap import dedent

import pytest

from watchtower import Change, ChangeKind, ConfigError, Item, MissingDependencyError
from watchtower.config import Config, load_config
from watchtower.core import WatcherBuilder
from watchtower.diffs import ItemDiff, TextDiff
from watchtower.filters import (
    NewItems,
    Not,
    Or,
    PriceBelow,
    TextContains,
)
from watchtower.notifiers import ConsoleNotifier
from watchtower.sources import FakeSource, RSSSource, WebPageSource


def _write_config(tmp_path: Path, text: str) -> Path:
    """Write YAML text to a config file in tmp_path."""
    config_file = tmp_path / "config.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(text, encoding="utf-8")
    return config_file


def test_load_example_config() -> None:
    """Test loading the official examples/config.yaml file."""
    config_path = Path(__file__).parents[2] / "examples" / "config.yaml"
    config = load_config(config_path)

    assert isinstance(config, Config)
    assert config.database == config_path.parent / "watchtower.db"
    assert len(config.watchers) == 2

    # Watcher 1
    w1 = config.watchers[0].build()
    assert w1.name == "Cheap flats without agencies"
    assert w1.interval == timedelta(seconds=30)
    assert isinstance(w1.source, WebPageSource)
    assert w1.source.url == "http://127.0.0.1:8000/listings"
    assert isinstance(w1.differ, ItemDiff)
    assert len(w1.filters) == 3
    assert isinstance(w1.filters[0], NewItems)
    assert isinstance(w1.filters[1], PriceBelow)
    assert isinstance(w1.filters[2], Not)

    cheap_direct = Change(kind=ChangeKind.NEW, item=Item(key="1", title="Direct flat", price=2500))
    expensive_direct = Change(
        kind=ChangeKind.NEW, item=Item(key="2", title="Direct flat", price=3500)
    )
    agency_flat = Change(
        kind=ChangeKind.NEW, item=Item(key="3", title="Estate Agency flat", price=2000)
    )
    assert w1.filters[1].matches(cheap_direct)
    assert not w1.filters[1].matches(expensive_direct)
    assert w1.filters[2].matches(cheap_direct)
    assert not w1.filters[2].matches(agency_flat)

    assert len(w1.notifiers) == 1
    assert isinstance(w1.notifiers[0], ConsoleNotifier)

    # Watcher 2
    w2 = config.watchers[1].build()
    assert w2.name == "Listings feed"
    assert w2.interval == timedelta(minutes=1)
    assert isinstance(w2.source, RSSSource)
    assert w2.source.url == "http://127.0.0.1:8000/feed.xml"
    assert isinstance(w2.differ, ItemDiff)
    assert len(w2.filters) == 1
    assert isinstance(w2.filters[0], Or)
    assert len(w2.notifiers) == 1
    assert isinstance(w2.notifiers[0], ConsoleNotifier)


def test_yaml_watcher_equals_python_builder_watcher(tmp_path: Path) -> None:
    """Test that a watcher built from YAML equals the same watcher built with WatcherBuilder."""
    yaml_file = _write_config(
        tmp_path,
        dedent("""
            database: app.db
            watchers:
              - name: Flat alerts
                source:
                  type: fake
                  contents: ["line 1", "line 2"]
                diff:
                  type: text
                interval: 15m
                filters:
                  - new_items
                  - price_below: 2500
                  - not:
                      text_contains: agency
                notify:
                  - type: console
            """),
    )

    config = load_config(yaml_file)
    from_yaml = config.watchers[0].build()

    from_python = (
        WatcherBuilder("Flat alerts")
        .source(FakeSource(contents=["line 1", "line 2"]))
        .diff(TextDiff())
        .every(timedelta(minutes=15))
        .only_if(
            NewItems(),
            PriceBelow(2500),
            Not(TextContains("agency")),
        )
        .notify(ConsoleNotifier())
        .build()
    )

    assert from_yaml.name == from_python.name
    assert from_yaml.interval == from_python.interval
    assert type(from_yaml.source) is type(from_python.source)
    assert type(from_yaml.differ) is type(from_python.differ)
    assert len(from_yaml.filters) == len(from_python.filters)
    assert [type(f) for f in from_yaml.filters] == [type(f) for f in from_python.filters]

    sample_changes = [
        Change(kind=ChangeKind.NEW, item=Item(key="1", title="Cheap private", price=2000)),
        Change(kind=ChangeKind.NEW, item=Item(key="2", title="Agency flat", price=2000)),
        Change(kind=ChangeKind.NEW, item=Item(key="3", title="Expensive flat", price=3000)),
        Change(kind=ChangeKind.CHANGED, item=Item(key="4", title="Changed flat", price=1500)),
    ]
    for change in sample_changes:
        yaml_results = [f.matches(change) for f in from_yaml.filters]
        python_results = [f.matches(change) for f in from_python.filters]
        assert yaml_results == python_results

    assert len(from_yaml.notifiers) == len(from_python.notifiers)
    assert type(from_yaml.notifiers[0]) is type(from_python.notifiers[0])


def test_relative_and_absolute_database_path(tmp_path: Path) -> None:
    """Test database path resolution for both relative and absolute paths."""
    rel_file = _write_config(
        tmp_path,
        dedent("""
            database: state.db
            watchers:
              - name: W
                source: { type: fake }
                diff: { type: text }
            """),
    )
    assert load_config(rel_file).database == tmp_path / "state.db"

    abs_db = tmp_path / "custom" / "abs.db"
    abs_file = _write_config(
        tmp_path / "nested_dir",
        dedent(f"""
            database: "{abs_db.as_posix()}"
            watchers:
              - name: W
                source: {{ type: fake }}
                diff: {{ type: text }}
            """),
    )
    assert load_config(abs_file).database == abs_db

    no_db_file = _write_config(
        tmp_path / "other_dir",
        dedent("""
            watchers:
              - name: W
                source: { type: fake }
                diff: { type: text }
            """),
    )
    assert load_config(no_db_file).database is None


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    """Test that a non-existent config file raises ConfigError."""
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_read_yaml_os_error_raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that OS errors when opening config file raise ConfigError."""
    file = _write_config(tmp_path, "watchers: []")

    def mock_open(*args: object, **kwargs: object) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", mock_open)
    with pytest.raises(ConfigError, match="Cannot read config file"):
        load_config(file)


def test_missing_optional_dependency_is_config_error(
    tmp_path: Path, no_desktop_notifier: None
) -> None:
    """A plugin needing an absent extra fails as ConfigError with watcher context."""
    config_file = _write_config(
        tmp_path,
        dedent("""
            watchers:
              - name: Flat alerts
                source: { type: fake, contents: ["offer"] }
                diff: { type: text }
                notify: [{ type: desktop }]
        """),
    )

    with pytest.raises(ConfigError, match="Watcher 'Flat alerts' key 'notify'") as caught:
        load_config(config_file)

    assert isinstance(caught.value.__cause__, MissingDependencyError)


@pytest.mark.parametrize(
    ("yaml_text", "match"),
    [
        ("watchers: [unclosed", "Invalid YAML"),
        ("- item1\n- item2", "must contain a mapping"),
        ("unknown_key: 123\nwatchers: []\n", "unknown key 'unknown_key'"),
        ("database: test.db", "lacks required key 'watchers'"),
        ("watchers: not_a_list", "key 'watchers' must be a list"),
        ("watchers: ['just a string']", "Watcher entry must be a mapping"),
        (
            dedent("""
                watchers:
                  - source: { type: fake }
                    diff: { type: text }
                """),
            "missing required key 'name'",
        ),
        ("watchers:\n  - name: 123\n", "Watcher key 'name' must be a non-empty string"),
        ("watchers:\n  - name: '   '\n", "Watcher key 'name' must be a non-empty string"),
        (
            dedent("""
                watchers:
                  - name: Dup
                    source: { type: fake }
                    diff: { type: text }
                  - name: Dup
                    source: { type: fake }
                    diff: { type: text }
                """),
            "Watcher 'Dup' key 'name': duplicate watcher name",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    typo_interval: 15m
                """),
            "Watcher 'W' has unknown key 'typo_interval'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    diff: { type: text }
                """),
            "Watcher 'W' missing required key 'source'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: 'not a dict'
                    diff: { type: text }
                """),
            "Watcher 'W' key 'source': must be a mapping",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { url: 'http://x.com' }
                    diff: { type: text }
                """),
            "Watcher 'W' key 'source': missing required key 'type'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: 123 }
                    diff: { type: text }
                """),
            "Watcher 'W' key 'source': 'type' must be a string",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: nonexistent_source }
                    diff: { type: text }
                """),
            "Watcher 'W' key 'source': unknown source plugin 'nonexistent_source'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake, invalid_kwarg: 123 }
                    diff: { type: text }
                """),
            "Watcher 'W' key 'source'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                """),
            "Watcher 'W' missing required key 'diff'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: 'not a dict'
                """),
            "Watcher 'W' key 'diff': must be a mapping",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { option: 1 }
                """),
            "Watcher 'W' key 'diff': missing required key 'type'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: 123 }
                """),
            "Watcher 'W' key 'diff': 'type' must be a string",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: nonexistent_differ }
                """),
            "Watcher 'W' key 'diff': unknown differ plugin 'nonexistent_differ'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text, invalid_param: 123 }
                """),
            "Watcher 'W' key 'diff'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    interval: -5m
                """),
            "Watcher 'W' key 'interval'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    interval: 30
                """),
            "Watcher 'W' key 'interval': Interval must be text",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    filters: 'not a list'
                """),
            "Watcher 'W' key 'filters': must be a list",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    filters:
                      - unknown_filter_name
                """),
            "Watcher 'W' key 'filters': unknown filter 'unknown_filter_name'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    notify: 'not a list'
                """),
            "Watcher 'W' key 'notify': must be a list",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    notify:
                      - 'just text'
                """),
            "Watcher 'W' key 'notify': must be a mapping",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    notify:
                      - { option: 1 }
                """),
            "Watcher 'W' key 'notify': missing required key 'type'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    notify:
                      - { type: 123 }
                """),
            "Watcher 'W' key 'notify': 'type' must be a string",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    notify:
                      - { type: nonexistent_notifier }
                """),
            "Watcher 'W' key 'notify': unknown notifier plugin 'nonexistent_notifier'",
        ),
        (
            dedent("""
                watchers:
                  - name: W
                    source: { type: fake }
                    diff: { type: text }
                    notify:
                      - { type: console, invalid_kw: 1 }
                """),
            "Watcher 'W' key 'notify'",
        ),
        (
            "database: 12345\nwatchers: []\n",
            "Config file key 'database' must be a non-empty string",
        ),
        ("database: ''\nwatchers: []\n", "Config file key 'database' must be a non-empty string"),
    ],
)
def test_invalid_config_raises_config_error(tmp_path: Path, yaml_text: str, match: str) -> None:
    """Test that invalid config files raise ConfigError with descriptive messages."""
    config_file = _write_config(tmp_path, yaml_text)
    with pytest.raises(ConfigError, match=match):
        load_config(config_file)
