"""Command-line interface for Watchtower."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from watchtower.core.watcher import Watcher
from watchtower.diffs.items import ItemDiff
from watchtower.diffs.text import TextDiff
from watchtower.errors import WatchtowerError
from watchtower.events import EventBus
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource
from watchtower.sources.webpage import WebPageSource
from watchtower.storage.snapshots import SnapshotStore

_DEMO_PAGES = [
    "Welcome to Watchtower Listings\n1. Flat in Stare Miasto - 3500 PLN\n",
    (
        "Welcome to Watchtower Listings\n"
        "1. Flat in Stare Miasto - 3500 PLN\n"
        "2. Flat in Krowodrza - 2800 PLN [NEW!]\n"
    ),
]

# 127.0.0.1 rather than localhost: localhost can resolve to IPv6 first, while
# the fake listings server listens on IPv4 only.
_LISTINGS_URL = "http://127.0.0.1:8000/listings"


def _build_demo_watcher() -> Watcher:
    """Create a watcher that replays the scripted demo pages.

    Returns:
        A watcher with a FakeSource, a TextDiff and a console notifier.
    """
    return Watcher(
        name="Krakow Flats Watcher",
        source=FakeSource(contents=_DEMO_PAGES),
        differ=TextDiff(),
        notifiers=[ConsoleNotifier()],
        event_bus=EventBus(),
    )


def _run_demo_check() -> int:
    """Run an end-to-end M1 demonstration check using FakeSource and TextDiff.

    Executes two consecutive checks:
    1. Initial check: establishes baseline (no changes reported per ADR-004).
    2. Second check: detects and prints unified text diff to the console.

    Returns:
        0 on success.
    """
    print("=== Watchtower M1 Demo: Foundations ===")
    watcher = _build_demo_watcher()

    print("\n[Step 1] Running initial check (establishing baseline)...")
    event1 = watcher.check_once()
    if event1 is None:
        print("-> Baseline captured successfully. No changes reported (as expected).")

    print("\n[Step 2] Running second check (detecting content change)...")
    event2 = watcher.check_once()
    if event2 is not None:
        print("-> Change successfully detected and printed above!")

    print("\n=== Demo completed successfully ===")
    return 0


def _build_listings_watcher(url: str, store: SnapshotStore) -> Watcher:
    """Create the M2 demo watcher for the fake listings server.

    The watcher is hard-coded until YAML config arrives in M3. Its source
    follows the HTML contract in examples/fake_listings/README.md.

    Args:
        url: Address of the listings page.
        store: Store keeping the last snapshot between runs.

    Returns:
        A watcher with a WebPageSource, an ItemDiff and a console notifier.
    """
    source = WebPageSource(
        url,
        selector=".offer",
        title_selector=".title",
        price_selector=".price",
        key_attribute="data-id",
    )
    return Watcher(
        name="Krakow flats",
        source=source,
        differ=ItemDiff(),
        notifiers=[ConsoleNotifier()],
        store=store,
    )


def _run_saved_check(watcher: Watcher, store: SnapshotStore) -> int:
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
        print(f"Baseline saved for {watcher.name!r}. Run again to see changes.")
    elif event is None:
        print(f"No changes for {watcher.name!r}.")
    return 0


def _run_file_check(file_path: Path, db_path: Path | None) -> int:
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
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1
    if db_path is None:
        print(
            "Error: checking a file needs --db PATH to compare it with the previous run",
            file=sys.stderr,
        )
        return 2

    store = SnapshotStore(db_path)
    watcher = Watcher(
        name=f"file:{file_path.resolve()}",
        source=FileSource(path=file_path),
        differ=TextDiff(),
        notifiers=[ConsoleNotifier()],
        store=store,
    )
    return _run_saved_check(watcher, store)


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser with its subcommands.

    Returns:
        The parser for the `watchtower` command.
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
        type=Path,
        default=None,
        help="File to check; without it, --db checks the demo listings page "
        "and no arguments run the built-in M1 demo",
    )
    check_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        metavar="PATH",
        help="SQLite file that keeps the last snapshot between runs",
    )
    check_parser.add_argument(
        "--url",
        default=_LISTINGS_URL,
        help=f"listings page checked by --db without a file (default: {_LISTINGS_URL})",
    )
    return parser


def _run_check(args: argparse.Namespace) -> int:
    """Run the variant of the `check` command chosen by the arguments.

    Args:
        args: Parsed arguments of the `check` command.

    Returns:
        Exit code of the check.

    Raises:
        WatchtowerError: If a source or the store fails.
    """
    if args.target is not None:
        return _run_file_check(args.target, args.db)
    if args.db is not None:
        store = SnapshotStore(args.db)
        return _run_saved_check(_build_listings_watcher(args.url, store), store)
    return _run_demo_check()


def main(argv: list[str] | None = None) -> int:
    """Run the `watchtower` command.

    Args:
        argv: Command-line arguments; None means `sys.argv[1:]`.

    Returns:
        Exit code: 0 on success, 1 on a Watchtower error, 2 on wrong usage.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "check":
        parser.print_help()
        return 0
    try:
        return _run_check(args)
    except WatchtowerError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
