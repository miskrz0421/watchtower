"""Importing the plugin modules a config file lists under `plugins`."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

from watchtower._errors import ConfigError

# Prefix of the `sys.modules` names of plugin files, so a file cannot replace a real module.
_FILE_MODULE_PREFIX = "watchtower_plugin_"


def _import_file(path: Path) -> None:
    """Run a plugin file once per process, as a module named after the file.

    Args:
        path: Absolute path of the `.py` file.

    Raises:
        ConfigError: If the file does not exist, or another file with the same
            name is already loaded.
    """
    name = _FILE_MODULE_PREFIX + path.stem
    loaded = sys.modules.get(name)
    if loaded is not None:
        if loaded.__file__ != str(path):
            msg = f"Plugin file {path} has the same name as the loaded {loaded.__file__}"
            raise ConfigError(msg)
        return
    spec = importlib.util.spec_from_file_location(name, path)
    if not path.is_file() or spec is None or spec.loader is None:
        msg = f"Plugin file not found: {path}"
        raise ConfigError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise


def _import_plugin(entry: str, config_dir: Path) -> None:
    """Import one `plugins` entry: a `.py` file or the name of an importable module.

    Args:
        entry: The entry from the config file.
        config_dir: Folder of the config file; relative file paths start there.

    Raises:
        ConfigError: If the plugin file is missing or clashes with a loaded one.
        Exception: Whatever the plugin module raises while it is imported.
    """
    if entry.endswith(".py"):
        _import_file((config_dir / entry).resolve())
    else:
        importlib.import_module(entry)


def load_plugins(entries: object, config_dir: Path) -> None:
    """Import every module listed under `plugins`, so that its plugins register themselves.

    A module is imported only once per process, so reloading the config does
    not register its plugins again (see ADR-035).

    Args:
        entries: Value of the `plugins` key: `.py` files and module names.
        config_dir: Folder of the config file; relative file paths start there.

    Raises:
        ConfigError: If the value is not a list of names, or a module cannot be imported.
    """
    if not isinstance(entries, list):
        msg = f"Config file key 'plugins' must be a list, got {entries!r}"
        raise ConfigError(msg)
    for entry in entries:
        if not isinstance(entry, str) or not entry:
            msg = f"Config file key 'plugins': each entry must be a non-empty string, got {entry!r}"
            raise ConfigError(msg)
        try:
            _import_plugin(entry, config_dir)
        except ConfigError:
            raise
        # A plugin is the user's own code and may raise anything while it is imported.
        except Exception as err:
            msg = f"Plugin {entry!r} cannot be loaded: {type(err).__name__}: {err}"
            raise ConfigError(msg) from err
