"""Command-line interface for Watchtower."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from watchtower import ChangeEvent, EventBus, WatchtowerError, list_plugins
from watchtower.config import Config, load_config
from watchtower.core import LoggingObserver, Scheduler, Watcher
from watchtower.storage import HistoryRecorder, HistoryStore, SnapshotStore

_LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def _configure_logging() -> None:
    """Show Watchtower's own log at INFO, and other libraries' only from WARNING."""
    logging.basicConfig(level=logging.WARNING, format=_LOG_FORMAT)
    logging.getLogger("watchtower").setLevel(logging.INFO)


def _open_database(database: Path | None, event_bus: EventBus) -> SnapshotStore | None:
    """Open the config's database for snapshots and start recording history in it.

    Args:
        database: SQLite file named in the config, or None if it names none.
        event_bus: Bus whose checks and changes are recorded.

    Returns:
        The snapshot store, or None when the config has no database.

    Raises:
        StorageError: If the database cannot be opened.
    """
    if database is None:
        return None
    HistoryRecorder(HistoryStore(database)).attach(event_bus)
    return SnapshotStore(database)


def _build_watchers(config: Config, event_bus: EventBus) -> list[Watcher]:
    """Build every watcher of a config, sharing one event bus and one database.

    Args:
        config: Loaded config file.
        event_bus: Bus all watchers publish on.

    Returns:
        The watchers, in file order.

    Raises:
        WatchtowerError: If the database cannot be opened or a watcher is incomplete.
    """
    store = _open_database(config.database, event_bus)
    return [builder.store(store).event_bus(event_bus).build() for builder in config.watchers]


def _describe_check(watcher_name: str, is_first_run: bool, event: ChangeEvent | None) -> str:
    """Say in one line what a check found.

    Args:
        watcher_name: Name of the checked watcher.
        is_first_run: Whether there was no snapshot to compare with.
        event: Changes the check reported, or None.

    Returns:
        The line to print.
    """
    if is_first_run:
        return f"{watcher_name}: baseline saved"
    if event is None:
        return f"{watcher_name}: no changes"
    return f"{watcher_name}: {event.summary}"


def _check_watcher(watcher: Watcher) -> bool:
    """Check one watcher and print what it found, or why it failed.

    The changes themselves are printed by the watcher's notifiers; the line
    printed here makes a quiet check visibly different from a broken one.

    Args:
        watcher: Watcher to check.

    Returns:
        True if the check succeeded.
    """
    try:
        is_first_run = watcher.store is None or watcher.store.load(watcher.name) is None
        event = watcher.check_once()
    except WatchtowerError as err:
        print(f"Error: {watcher.name}: {err}", file=sys.stderr)
        return False
    print(_describe_check(watcher.name, is_first_run, event))
    return True


def _check_command(args: argparse.Namespace) -> int:
    """Check every watcher of a config file once.

    A failing watcher is reported and the others are still checked.

    Args:
        args: Parsed arguments with the `config` path.

    Returns:
        0 if every check succeeded, 1 otherwise.

    Raises:
        WatchtowerError: If the config or the database cannot be used.
    """
    watchers = _build_watchers(load_config(args.config), EventBus())
    results = [_check_watcher(watcher) for watcher in watchers]
    return 0 if all(results) else 1


def _run_command(args: argparse.Namespace) -> int:
    """Run the watchers of a config file at their intervals until Ctrl+C.

    Args:
        args: Parsed arguments with the `config` path.

    Returns:
        0 when stopped with Ctrl+C.

    Raises:
        WatchtowerError: If the config or the database cannot be used.
    """
    event_bus = EventBus()
    LoggingObserver().attach(event_bus)
    scheduler = Scheduler()
    watchers = _build_watchers(load_config(args.config), event_bus)
    for watcher in watchers:
        scheduler.add(watcher)

    _configure_logging()
    print(f"Running {len(watchers)} watcher(s). Press Ctrl+C to stop.")
    try:
        scheduler.run_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    return 0


def _plugins_command(args: argparse.Namespace) -> int:
    """Print the names of the registered plugins, by kind.

    Args:
        args: Parsed arguments; the command takes none.

    Returns:
        0.
    """
    for kind, names in list_plugins().items():
        print(f"{kind}: {', '.join(names)}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser with its subcommands.

    Each subcommand stores the function that runs it as `handler`.

    Returns:
        The parser for the `watchtower` command.
    """
    parser = argparse.ArgumentParser(
        prog="watchtower",
        description="A plugin-based monitoring framework: watch anything, detect changes, react.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    check_parser = subparsers.add_parser("check", help="Check every watcher of a config once")
    check_parser.add_argument("config", type=Path, help="YAML config file")
    check_parser.set_defaults(handler=_check_command)

    run_parser = subparsers.add_parser("run", help="Run the watchers of a config until Ctrl+C")
    run_parser.add_argument("config", type=Path, help="YAML config file")
    run_parser.set_defaults(handler=_run_command)

    plugins_parser = subparsers.add_parser("plugins", help="List the registered plugins")
    plugins_parser.set_defaults(handler=_plugins_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the `watchtower` command.

    Args:
        argv: Command-line arguments; None means `sys.argv[1:]`.

    Returns:
        Exit code: 0 on success, 1 on a Watchtower error, 2 on wrong usage.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    try:
        exit_code: int = args.handler(args)
    except WatchtowerError as err:
        print(f"Error: {err}", file=sys.stderr)
        exit_code = 1
    return exit_code
