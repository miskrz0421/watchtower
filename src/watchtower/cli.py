"""Command-line interface for Watchtower."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from watchtower.core.watcher import Watcher
from watchtower.diffs.text import TextDiff
from watchtower.errors import WatchtowerError
from watchtower.events import EventBus
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource
from watchtower.storage.snapshots import SnapshotStore

DEMO_PAGES = [
    "Welcome to Watchtower Listings\n1. Flat in Stare Miasto - 3500 PLN\n",
    (
        "Welcome to Watchtower Listings\n"
        "1. Flat in Stare Miasto - 3500 PLN\n"
        "2. Flat in Krowodrza - 2800 PLN [NEW!]\n"
    ),
]


def build_demo_watcher() -> Watcher:
    """Create a watcher that replays the scripted demo pages."""
    return Watcher(
        name="Krakow Flats Watcher",
        source=FakeSource(contents=DEMO_PAGES),
        differ=TextDiff(),
        notifiers=[ConsoleNotifier(stream=sys.stdout)],
        event_bus=EventBus(),
    )


def run_demo_check() -> int:
    """Run an end-to-end M1 demonstration check using FakeSource and TextDiff.

    Executes two consecutive checks:
    1. Initial check: establishes baseline (no changes reported per ADR-004).
    2. Second check: detects and prints unified text diff to the console.

    Returns:
        0 on success.
    """
    sys.stdout.write("=== Watchtower M1 Demo: Foundations ===\n")
    watcher = build_demo_watcher()

    sys.stdout.write("\n[Step 1] Running initial check (establishing baseline)...\n")
    event1 = watcher.check_once()
    if event1 is None:
        sys.stdout.write("-> Baseline captured successfully. No changes reported (as expected).\n")

    sys.stdout.write("\n[Step 2] Running second check (detecting content change)...\n")
    event2 = watcher.check_once()
    if event2 is not None:
        sys.stdout.write("-> Change successfully detected and printed above!\n")

    sys.stdout.write("\n=== Demo completed successfully ===\n")
    return 0


def run_saved_check(watcher: Watcher, store: SnapshotStore) -> int:
    """Run one check of a watcher whose state is kept in a store.

    Changes are printed by the watcher's notifiers. This function only says
    when there was nothing to print, so a quiet run never looks like it did
    nothing by mistake.

    Args:
        watcher: Watcher to check; it must use `store`.
        store: Store holding the watcher's previous snapshot.

    Returns:
        0 on success.

    Raises:
        WatchtowerError: If the source or the store fails.
    """
    is_first_run = store.load(watcher.name) is None
    event = watcher.check_once()

    if is_first_run:
        sys.stdout.write(f"Baseline saved for {watcher.name!r}. Run again to see changes.\n")
    elif event is None:
        sys.stdout.write(f"No changes for {watcher.name!r}.\n")
    return 0


def run_file_check(file_path: Path, db_path: Path | None) -> int:
    """Check a local file for changes since the previous run.

    Args:
        file_path: Path to the monitored file.
        db_path: SQLite file keeping the previous contents. Required, since
            without it there is nothing to compare with.

    Returns:
        0 on success, non-zero on failure.

    Raises:
        WatchtowerError: If the file cannot be read or the store fails.
    """
    if not file_path.exists():
        sys.stderr.write(f"Error: File not found: {file_path}\n")
        return 1
    if db_path is None:
        sys.stderr.write(
            "Error: checking a file needs --db PATH to compare it with the previous run\n"
        )
        return 2

    store = SnapshotStore(db_path)
    watcher = Watcher(
        name=f"file:{file_path.resolve()}",
        source=FileSource(path=file_path),
        differ=TextDiff(),
        notifiers=[ConsoleNotifier(stream=sys.stdout)],
        store=store,
    )
    return run_saved_check(watcher, store)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint for watchtower.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code integer (0 for success).
    """
    parser = argparse.ArgumentParser(
        prog="watchtower",
        description="A plugin-based monitoring framework: watch anything, detect changes, react.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    check_parser = subparsers.add_parser("check", help="Run watchers once")
    check_parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Path to a file to check, or omitted to run the built-in M1 demo",
    )
    check_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        metavar="PATH",
        help="SQLite file that keeps the last snapshot between runs",
    )

    args = parser.parse_args(argv)

    if args.command == "check":
        try:
            if args.target:
                return run_file_check(Path(args.target), args.db)
            return run_demo_check()
        except WatchtowerError as err:
            sys.stderr.write(f"Error: {err}\n")
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
