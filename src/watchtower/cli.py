"""Command-line interface for Watchtower."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from watchtower.core.watcher import Watcher
from watchtower.diffs.text import TextDiff
from watchtower.events import EventBus
from watchtower.notifiers.console import ConsoleNotifier
from watchtower.sources.fake import FakeSource
from watchtower.sources.file import FileSource


def run_demo_check() -> int:
    """Run an end-to-end M1 demonstration check using FakeSource and TextDiff.

    Executes two consecutive checks:
    1. Initial check: establishes baseline (no changes reported per ADR-004).
    2. Second check: detects and prints unified text diff to the console.

    Returns:
        0 on success.
    """
    sys.stdout.write("=== Watchtower M1 Demo: Foundations ===\n")
    bus = EventBus()
    notifier = ConsoleNotifier(stream=sys.stdout)
    differ = TextDiff()

    scripted_pages = [
        "Welcome to Watchtower Listings\n1. Flat in Stare Miasto - 3500 PLN\n",
        (
            "Welcome to Watchtower Listings\n"
            "1. Flat in Stare Miasto - 3500 PLN\n"
            "2. Flat in Krowodrza - 2800 PLN [NEW!]\n"
        ),
    ]

    source = FakeSource(contents=scripted_pages)
    watcher = Watcher(
        name="Krakow Flats Watcher",
        source=source,
        differ=differ,
        notifiers=[notifier],
        event_bus=bus,
    )

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


def run_file_check(file_path: Path) -> int:
    """Run a check against a specific local file.

    Args:
        file_path: Path to the monitored file.

    Returns:
        0 on success, non-zero on failure.
    """
    if not file_path.exists():
        sys.stderr.write(f"Error: File not found: {file_path}\n")
        return 1

    source = FileSource(path=file_path)
    differ = TextDiff()
    notifier = ConsoleNotifier()
    watcher = Watcher(
        name=f"File: {file_path.name}",
        source=source,
        differ=differ,
        notifiers=[notifier],
    )
    watcher.check_once()
    return 0


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

    args = parser.parse_args(argv)

    if args.command == "check":
        if args.target:
            return run_file_check(Path(args.target))
        return run_demo_check()

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
