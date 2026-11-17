"""Start of the desktop app."""

from __future__ import annotations

from pathlib import Path


def run_gui(config_path: Path) -> int:
    """Run the watchers of a config file with the tray icon and window, until Quit.

    Args:
        config_path: YAML config file.

    Returns:
        The exit code of the Qt event loop.

    Raises:
        WatchtowerError: If the config or the database cannot be used.
    """
    raise NotImplementedError
