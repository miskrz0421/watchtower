"""Tests for loading the plugin modules a config file lists."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from watchtower import ConfigError, list_plugins
from watchtower.config import load_config

pytestmark = pytest.mark.usefixtures("forget_plugins")

_PLUGIN = dedent('''\
    from watchtower import ChangeEvent, Notifier, register_notifier


    @register_notifier("shout")
    class ShoutNotifier(Notifier):
        """Print the summary in capitals."""

        def send(self, event: ChangeEvent) -> None:
            """Print the summary in capitals."""
            print(event.summary.upper())
''')


def _write(path: Path, text: str) -> Path:
    """Write text to a file, creating its folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _config(folder: Path, plugins: str) -> Path:
    """Write a config whose one watcher notifies through the `shout` plugin."""
    return _write(
        folder / "config.yaml",
        dedent(f"""\
            plugins: {plugins}
            watchers:
              - name: Notes
                source: {{ type: fake, contents: [a] }}
                diff: {{ type: text }}
                notify: [{{ type: shout }}]
        """),
    )


def test_plugin_file_is_relative_to_the_config_file(tmp_path: Path) -> None:
    """A watcher can use a notifier from a file listed under plugins."""
    _write(tmp_path / "plugins" / "shout.py", _PLUGIN)

    config = load_config(_config(tmp_path, "[plugins/shout.py]"))

    notifier = config.watchers[0].build().notifiers[0]
    assert type(notifier).__name__ == "ShoutNotifier"
    assert "shout" in list_plugins("notifier")["notifier"]


def test_loading_the_config_again_does_not_register_the_plugin_twice(tmp_path: Path) -> None:
    """Reloading a config skips the plugin files that are already loaded."""
    _write(tmp_path / "shout.py", _PLUGIN)
    config_file = _config(tmp_path, "[shout.py]")

    load_config(config_file)
    config = load_config(config_file)

    assert len(config.watchers) == 1


def test_module_name_is_imported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry without .py is the name of an importable module."""
    _write(tmp_path / "modules" / "my_plugins.py", _PLUGIN)
    monkeypatch.syspath_prepend(tmp_path / "modules")

    config = load_config(_config(tmp_path, "[my_plugins]"))

    assert len(config.watchers) == 1


def test_missing_plugin_file_is_a_config_error(tmp_path: Path) -> None:
    """A listed file that does not exist is reported with its path."""
    with pytest.raises(ConfigError, match="Plugin file not found: .*missing.py"):
        load_config(_config(tmp_path, "[missing.py]"))


def test_missing_module_is_a_config_error(tmp_path: Path) -> None:
    """A module that cannot be found is reported with the entry."""
    with pytest.raises(ConfigError, match="'my_missing' cannot be loaded: ModuleNotFoundError"):
        load_config(_config(tmp_path, "[my_missing]"))


def test_failing_plugin_is_a_config_error_and_can_be_fixed(tmp_path: Path) -> None:
    """An error in a plugin file is reported, and the fixed file loads on the next try."""
    plugin = _write(tmp_path / "shout.py", "raise RuntimeError('broken plugin')\n")
    config_file = _config(tmp_path, "[shout.py]")
    with pytest.raises(ConfigError, match="'shout.py' cannot be loaded: RuntimeError: broken"):
        load_config(config_file)

    _write(plugin, _PLUGIN)

    assert len(load_config(config_file).watchers) == 1


def test_two_plugin_files_with_the_same_name_are_a_config_error(tmp_path: Path) -> None:
    """A second file named like a loaded one is rejected instead of silently skipped."""
    _write(tmp_path / "a" / "shout.py", _PLUGIN)
    _write(tmp_path / "b" / "shout.py", _PLUGIN)
    load_config(_config(tmp_path, "[a/shout.py]"))

    with pytest.raises(ConfigError, match="same name as the loaded"):
        load_config(_config(tmp_path, "[b/shout.py]"))


@pytest.mark.parametrize(
    ("plugins", "message"),
    [
        ("shout.py", "must be a list"),
        ("[1]", "must be a non-empty string, got 1"),
        ("['']", "must be a non-empty string, got ''"),
    ],
)
def test_plugins_must_be_a_list_of_names(tmp_path: Path, plugins: str, message: str) -> None:
    """The plugins key holds a list of non-empty strings."""
    with pytest.raises(ConfigError, match=message):
        load_config(_config(tmp_path, plugins))
