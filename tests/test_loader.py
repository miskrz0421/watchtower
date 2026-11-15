"""Tests for loading watcher configuration from YAML."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from watchtower.config.loader import Config, load_config
from watchtower.core.builder import WatcherBuilder
from watchtower.diffs.items import ItemDiff
from watchtower.diffs.text import TextDiff
from watchtower.errors import ConfigError
from watchtower.filters import (
    And,
    NewItems,
    Not,
    Or,
    PriceAbove,
    PriceBelow,
    TextContains,
)
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.sources.fake import FakeSource
from watchtower.sources.rss import RSSSource
from watchtower.sources.webpage import WebPageSource


def test_load_example_config() -> None:
    """Test loading the official examples/config.yaml file."""
    config_path = Path("examples/config.yaml")
    config = load_config(config_path)

    assert isinstance(config, Config)
    assert config.database == Path("examples/watchtower.db")
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
    assert w1.filters[1]._limit == 3000
    assert isinstance(w1.filters[2], Not)
    assert isinstance(w1.filters[2]._inner, TextContains)
    assert w1.filters[2]._inner._phrase == "agency"
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
    yaml_file = tmp_path / "test_config.yaml"
    # Note: watchtower_settings is unknown, so fix content without unknown keys
    yaml_file.write_text(
        """
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
""",
        encoding="utf-8",
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
    assert isinstance(from_yaml.filters[0], NewItems)
    assert isinstance(from_python.filters[0], NewItems)
    assert isinstance(from_yaml.filters[1], PriceBelow)
    assert isinstance(from_python.filters[1], PriceBelow)
    assert from_yaml.filters[1]._limit == from_python.filters[1]._limit
    assert isinstance(from_yaml.filters[2], Not)
    assert isinstance(from_python.filters[2], Not)
    assert isinstance(from_yaml.filters[2]._inner, TextContains)
    assert isinstance(from_python.filters[2]._inner, TextContains)
    assert from_yaml.filters[2]._inner._phrase == from_python.filters[2]._inner._phrase
    assert len(from_yaml.notifiers) == len(from_python.notifiers)
    assert type(from_yaml.notifiers[0]) is type(from_python.notifiers[0])


def test_nested_composite_filters(tmp_path: Path) -> None:
    """Test loading deeply nested composite filters with all, any, and not."""
    yaml_file = tmp_path / "nested.yaml"
    yaml_file.write_text(
        """
watchers:
  - name: Complex filter watcher
    source: { type: fake }
    diff: { type: text }
    filters:
      - all:
          - new_items
          - any:
              - price_below: 2000
              - price_above: 6000
          - not: { text_contains: quiet }
""",
        encoding="utf-8",
    )

    config = load_config(yaml_file)
    watcher = config.watchers[0].build()

    assert len(watcher.filters) == 1
    top = watcher.filters[0]
    assert isinstance(top, And)
    assert len(top._filters) == 3
    assert isinstance(top._filters[0], NewItems)
    assert isinstance(top._filters[1], Or)
    assert len(top._filters[1]._filters) == 2
    assert isinstance(top._filters[1]._filters[0], PriceBelow)
    assert isinstance(top._filters[1]._filters[1], PriceAbove)
    assert isinstance(top._filters[2], Not)
    assert isinstance(top._filters[2]._inner, TextContains)


def test_relative_and_absolute_database_path(tmp_path: Path) -> None:
    """Test database path resolution for both relative and absolute paths."""
    rel_file = tmp_path / "rel.yaml"
    rel_file.write_text(
        """
database: state.db
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
""",
        encoding="utf-8",
    )
    assert load_config(rel_file).database == tmp_path / "state.db"

    abs_db = tmp_path / "custom" / "abs.db"
    abs_file = tmp_path / "abs.yaml"
    abs_file.write_text(
        f"""
database: "{abs_db.as_posix()}"
watchers:
  - name: W
    source: {{ type: fake }}
    diff: {{ type: text }}
""",
        encoding="utf-8",
    )
    assert load_config(abs_file).database == abs_db

    no_db_file = tmp_path / "no_db.yaml"
    no_db_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
""",
        encoding="utf-8",
    )
    assert load_config(no_db_file).database is None


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    """Test that a non-existent config file raises ConfigError."""
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_invalid_yaml_syntax_raises_config_error(tmp_path: Path) -> None:
    """Test that malformed YAML syntax raises ConfigError."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("watchers: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(bad_file)


def test_top_level_not_a_mapping_raises_config_error(tmp_path: Path) -> None:
    """Test that YAML containing a list at top level raises ConfigError."""
    bad_file = tmp_path / "list.yaml"
    bad_file.write_text("- item1\n- item2", encoding="utf-8")

    with pytest.raises(ConfigError, match="must contain a mapping"):
        load_config(bad_file)


def test_unknown_top_level_key_raises_config_error(tmp_path: Path) -> None:
    """Test that unrecognized top-level keys raise ConfigError."""
    bad_file = tmp_path / "unknown_top.yaml"
    bad_file.write_text(
        """
unknown_key: 123
watchers: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown key 'unknown_key'"):
        load_config(bad_file)


def test_missing_watchers_key_raises_config_error(tmp_path: Path) -> None:
    """Test that config without watchers key raises ConfigError."""
    bad_file = tmp_path / "no_watchers.yaml"
    bad_file.write_text("database: test.db", encoding="utf-8")

    with pytest.raises(ConfigError, match="lacks required key 'watchers'"):
        load_config(bad_file)


def test_watchers_not_a_list_raises_config_error(tmp_path: Path) -> None:
    """Test that non-list watchers key raises ConfigError."""
    bad_file = tmp_path / "watchers_not_list.yaml"
    bad_file.write_text("watchers: not_a_list", encoding="utf-8")

    with pytest.raises(ConfigError, match="key 'watchers' must be a list"):
        load_config(bad_file)


def test_watcher_entry_not_a_mapping_raises_config_error(tmp_path: Path) -> None:
    """Test that a non-mapping entry in watchers raises ConfigError."""
    bad_file = tmp_path / "watcher_string.yaml"
    bad_file.write_text("watchers: ['just a string']", encoding="utf-8")

    with pytest.raises(ConfigError, match="Watcher entry must be a mapping"):
        load_config(bad_file)


def test_watcher_missing_name_raises_config_error(tmp_path: Path) -> None:
    """Test that a watcher entry without name raises ConfigError."""
    bad_file = tmp_path / "no_name.yaml"
    bad_file.write_text(
        """
watchers:
  - source: { type: fake }
    diff: { type: text }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="missing required key 'name'"):
        load_config(bad_file)


def test_duplicate_watcher_name_raises_config_error(tmp_path: Path) -> None:
    """Test that duplicate watcher names raise ConfigError naming watcher and key."""
    bad_file = tmp_path / "duplicate_name.yaml"
    bad_file.write_text(
        """
watchers:
  - name: Duplicate
    source: { type: fake }
    diff: { type: text }
  - name: Duplicate
    source: { type: fake }
    diff: { type: text }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'Duplicate' key 'name': duplicate watcher name"):
        load_config(bad_file)


def test_watcher_unknown_key_raises_config_error(tmp_path: Path) -> None:
    """Test that an unknown key in a watcher entry raises ConfigError."""
    bad_file = tmp_path / "unknown_key.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    typo_interval: 15m
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' has unknown key 'typo_interval'"):
        load_config(bad_file)


def test_watcher_missing_source_raises_config_error(tmp_path: Path) -> None:
    """Test that a watcher missing source raises ConfigError."""
    bad_file = tmp_path / "no_source.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    diff: { type: text }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' missing required key 'source'"):
        load_config(bad_file)


def test_watcher_invalid_source_raises_config_error(tmp_path: Path) -> None:
    """Test that non-mapping or invalid source raises ConfigError."""
    bad_file = tmp_path / "bad_source.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: "not a dict"
    diff: { type: text }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'source': must be a mapping"):
        load_config(bad_file)


def test_watcher_source_missing_type_raises_config_error(tmp_path: Path) -> None:
    """Test that source without type raises ConfigError."""
    bad_file = tmp_path / "no_source_type.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { url: "http://example.com" }
    diff: { type: text }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'source': missing required key 'type'"):
        load_config(bad_file)


def test_watcher_source_unknown_plugin_raises_config_error(tmp_path: Path) -> None:
    """Test that an unknown source plugin raises ConfigError."""
    bad_file = tmp_path / "unknown_source.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: nonexistent_source }
    diff: { type: text }
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'source': unknown source plugin 'nonexistent_source'"
    ):
        load_config(bad_file)


def test_watcher_missing_diff_raises_config_error(tmp_path: Path) -> None:
    """Test that a watcher missing diff raises ConfigError."""
    bad_file = tmp_path / "no_diff.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' missing required key 'diff'"):
        load_config(bad_file)


def test_watcher_invalid_diff_raises_config_error(tmp_path: Path) -> None:
    """Test that non-mapping diff raises ConfigError."""
    bad_file = tmp_path / "bad_diff.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: "not a dict"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'diff': must be a mapping"):
        load_config(bad_file)


def test_watcher_diff_missing_type_raises_config_error(tmp_path: Path) -> None:
    """Test that diff without type raises ConfigError."""
    bad_file = tmp_path / "no_diff_type.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { option: 1 }
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'diff': missing required key 'type'"):
        load_config(bad_file)


def test_watcher_diff_unknown_plugin_raises_config_error(tmp_path: Path) -> None:
    """Test that an unknown differ plugin raises ConfigError."""
    bad_file = tmp_path / "unknown_diff.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: nonexistent_differ }
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'diff': unknown differ plugin 'nonexistent_differ'"
    ):
        load_config(bad_file)


def test_watcher_invalid_interval_raises_config_error(tmp_path: Path) -> None:
    """Test that invalid interval raises ConfigError naming watcher and key."""
    bad_file = tmp_path / "bad_interval.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    interval: -5m
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'interval'"):
        load_config(bad_file)


def test_watcher_filters_not_a_list_raises_config_error(tmp_path: Path) -> None:
    """Test that non-list filters raise ConfigError."""
    bad_file = tmp_path / "bad_filters.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters: "not a list"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'filters': must be a list"):
        load_config(bad_file)


def test_watcher_filter_unknown_plugin_raises_config_error(tmp_path: Path) -> None:
    """Test that unknown filter plugin raises ConfigError."""
    bad_file = tmp_path / "unknown_filter.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - unknown_filter_name
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'filters': unknown filter 'unknown_filter_name'"
    ):
        load_config(bad_file)


def test_watcher_filter_multiple_keys_raises_config_error(tmp_path: Path) -> None:
    """Test that a filter mapping with multiple keys raises ConfigError."""
    bad_file = tmp_path / "multi_key_filter.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - { price_below: 3000, price_above: 1000 }
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'filters': filter entry must have exactly one key"
    ):
        load_config(bad_file)


def test_watcher_filter_empty_composite_raises_config_error(tmp_path: Path) -> None:
    """Test that empty all or any composite filter raises ConfigError."""
    bad_file = tmp_path / "empty_all.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - all: []
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'filters': 'all' requires at least one filter"
    ):
        load_config(bad_file)


def test_watcher_notify_not_a_list_raises_config_error(tmp_path: Path) -> None:
    """Test that non-list notify raises ConfigError."""
    bad_file = tmp_path / "bad_notify.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    notify: "not a list"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Watcher 'W' key 'notify': must be a list"):
        load_config(bad_file)


def test_watcher_notify_unknown_plugin_raises_config_error(tmp_path: Path) -> None:
    """Test that unknown notifier plugin raises ConfigError."""
    bad_file = tmp_path / "unknown_notifier.yaml"
    bad_file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    notify:
      - { type: nonexistent_notifier }
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError,
        match="Watcher 'W' key 'notify': unknown notifier plugin 'nonexistent_notifier'",
    ):
        load_config(bad_file)


def test_read_yaml_os_error_raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that OS errors when opening config file raise ConfigError."""
    file = tmp_path / "test.yaml"
    file.write_text("watchers: []", encoding="utf-8")

    def mock_open(*args: object, **kwargs: object) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "open", mock_open)
    with pytest.raises(ConfigError, match="Cannot read config file"):
        load_config(file)


def test_database_key_not_string_raises_config_error(tmp_path: Path) -> None:
    """Test that non-string database key raises ConfigError."""
    file = tmp_path / "bad_db.yaml"
    file.write_text("database: 12345\nwatchers: []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Config file key 'database' must be a non-empty string"):
        load_config(file)


def test_database_key_empty_raises_config_error(tmp_path: Path) -> None:
    """Test that whitespace database key raises ConfigError."""
    file = tmp_path / "empty_db.yaml"
    file.write_text("database: '   '\nwatchers: []\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Config file key 'database' must be a non-empty string"):
        load_config(file)


def test_watcher_name_not_string_raises_config_error(tmp_path: Path) -> None:
    """Test that non-string watcher name raises ConfigError."""
    file = tmp_path / "bad_name.yaml"
    file.write_text("watchers:\n  - name: 123\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Watcher key 'name' must be a non-empty string"):
        load_config(file)


def test_watcher_name_empty_raises_config_error(tmp_path: Path) -> None:
    """Test that whitespace watcher name raises ConfigError."""
    file = tmp_path / "empty_name.yaml"
    file.write_text("watchers:\n  - name: '   '\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Watcher key 'name' must be a non-empty string"):
        load_config(file)


def test_watcher_interval_not_string_raises_config_error(tmp_path: Path) -> None:
    """Test that non-string interval raises ConfigError."""
    file = tmp_path / "bad_interval_type.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    interval: 30
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'interval': expected text"):
        load_config(file)


def test_source_type_not_string_raises_config_error(tmp_path: Path) -> None:
    """Test that non-string source type raises ConfigError."""
    file = tmp_path / "source_type_num.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: 123 }
    diff: { type: text }
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'source': 'type' must be a string"):
        load_config(file)


def test_source_invalid_arguments_raises_config_error(tmp_path: Path) -> None:
    """Test that unexpected keyword arguments for source raise ConfigError."""
    file = tmp_path / "source_invalid_arg.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake, invalid_kwarg: 123 }
    diff: { type: text }
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'source'"):
        load_config(file)


def test_diff_type_not_string_raises_config_error(tmp_path: Path) -> None:
    """Test that non-string diff type raises ConfigError."""
    file = tmp_path / "diff_type_num.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: 123 }
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'diff': 'type' must be a string"):
        load_config(file)


def test_diff_invalid_arguments_raises_config_error(tmp_path: Path) -> None:
    """Test that unexpected keyword arguments for diff raise ConfigError."""
    file = tmp_path / "diff_invalid_arg.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text, invalid_param: 123 }
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'diff'"):
        load_config(file)


def test_notify_entry_not_a_mapping_raises_config_error(tmp_path: Path) -> None:
    """Test that non-mapping notify entry raises ConfigError."""
    file = tmp_path / "notify_not_mapping.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    notify:
      - "just text"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'notify': entry must be a mapping"):
        load_config(file)


def test_notify_entry_missing_type_raises_config_error(tmp_path: Path) -> None:
    """Test that notify entry without type raises ConfigError."""
    file = tmp_path / "notify_missing_type.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    notify:
      - { option: 1 }
""",
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'notify': entry missing required key 'type'"
    ):
        load_config(file)


def test_notify_entry_type_not_string_raises_config_error(tmp_path: Path) -> None:
    """Test that notify entry with non-string type raises ConfigError."""
    file = tmp_path / "notify_type_num.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    notify:
      - { type: 123 }
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'notify': 'type' must be a string"):
        load_config(file)


def test_notify_invalid_arguments_raises_config_error(tmp_path: Path) -> None:
    """Test that unexpected keyword arguments for notify raise ConfigError."""
    file = tmp_path / "notify_invalid_arg.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    notify:
      - { type: console, invalid_kw: 1 }
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'notify'"):
        load_config(file)


def test_filter_string_invalid_arguments_raises_config_error(tmp_path: Path) -> None:
    """Test that string filter without required arguments raises ConfigError."""
    file = tmp_path / "filter_no_arg.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - price_below
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'filters': filter 'price_below'"):
        load_config(file)


def test_filter_all_not_a_list_raises_config_error(tmp_path: Path) -> None:
    """Test that composite all filter with non-list value raises ConfigError."""
    file = tmp_path / "filter_all_non_list.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - all: "not a list"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'filters': 'all' requires a list"):
        load_config(file)


def test_filter_not_list_multiple_items_raises_config_error(tmp_path: Path) -> None:
    """Test that not filter with list of multiple entries raises ConfigError."""
    file = tmp_path / "filter_not_multiple.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - not: [new_items, new_items]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'filters': 'not' requires exactly one"):
        load_config(file)


def test_filter_not_list_of_one_item_works(tmp_path: Path) -> None:
    """Test that not filter with single-element list works."""
    file = tmp_path / "filter_not_single_list.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - not: [new_items]
""",
        encoding="utf-8",
    )
    config = load_config(file)
    w = config.watchers[0].build()
    assert len(w.filters) == 1
    assert isinstance(w.filters[0], Not)


def test_filter_leaf_mapping_unknown_filter_raises_config_error(tmp_path: Path) -> None:
    """Test that single-key mapping with unknown filter name raises ConfigError."""
    file = tmp_path / "filter_unknown_map.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - unknown_rule: 123
""",
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'filters': unknown filter 'unknown_rule'"
    ):
        load_config(file)


def test_filter_leaf_mapping_invalid_arg_raises_config_error(tmp_path: Path) -> None:
    """Test that single-key mapping with invalid argument raises ConfigError."""
    file = tmp_path / "filter_invalid_arg.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - matches: "[unclosed regex"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Watcher 'W' key 'filters': filter 'matches'"):
        load_config(file)


def test_filter_entry_invalid_type_raises_config_error(tmp_path: Path) -> None:
    """Test that filter entry of invalid type raises ConfigError."""
    file = tmp_path / "filter_number.yaml"
    file.write_text(
        """
watchers:
  - name: W
    source: { type: fake }
    diff: { type: text }
    filters:
      - 12345
""",
        encoding="utf-8",
    )
    with pytest.raises(
        ConfigError, match="Watcher 'W' key 'filters': filter entry must be a name or mapping"
    ):
        load_config(file)
