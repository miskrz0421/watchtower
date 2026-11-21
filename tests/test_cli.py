"""Tests for the watchtower CLI."""

from __future__ import annotations

import logging
import socket
from pathlib import Path
from textwrap import dedent

import pytest

from conftest import SAMPLE_LISTINGS, FakeListings
from watchtower import EventBus
from watchtower.cli import main
from watchtower.core import Scheduler
from watchtower.storage import HistoryStore


def _write_config(folder: Path, text: str) -> Path:
    """Write a config file into the folder and return its path."""
    config = folder / "config.yaml"
    config.write_text(text, encoding="utf-8")
    return config


def _file_config(folder: Path, watched: Path, database: str | None = "watchtower.db") -> Path:
    """Write a config with one text watcher on a local file."""
    database_line = f"database: {database}\n" if database is not None else ""
    return _write_config(
        folder,
        database_line
        + dedent(f"""
            watchers:
              - name: Notes
                source: {{ type: file, path: "{watched.as_posix()}" }}
                diff: {{ type: text }}
                notify: [{{ type: console }}]
            """),
    )


def _flats_config(folder: Path, base_url: str) -> Path:
    """Write the demo config: new flats under 3000 without agencies."""
    return _write_config(
        folder,
        dedent(f"""
            database: watchtower.db
            watchers:
              - name: Cheap flats
                source:
                  type: webpage
                  url: "{base_url}/listings"
                  selector: ".offer"
                  title_selector: ".title"
                  price_selector: ".price"
                  key_attribute: "data-id"
                interval: 30s
                diff: {{ type: items }}
                filters:
                  - new_items
                  - price_below: 3000
                  - not: {{ text_contains: agency }}
                notify: [{{ type: console }}]
            """),
    )


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that watchtower without a command prints the help text."""
    assert main([]) == 0
    assert "usage: watchtower" in capsys.readouterr().out


def test_plugins_lists_every_kind(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that the plugins command prints the registered names by kind."""
    assert main(["plugins"]) == 0
    out = capsys.readouterr().out
    assert "source: fake, file, json_api, rss, webpage" in out
    assert "differ: items, text" in out
    assert "notifier: console" in out


def test_check_reports_missing_optional_dependency(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], no_desktop_notifier: None
) -> None:
    """A config needing an absent extra fails with a clear error, not a traceback."""
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")
    config = _write_config(
        tmp_path,
        dedent(f"""
            watchers:
              - name: Notes
                source: {{ type: file, path: "{watched.as_posix()}" }}
                diff: {{ type: text }}
                notify: [{{ type: desktop }}]
        """),
    )

    assert main(["check", str(config)]) == 1
    err = capsys.readouterr().err
    assert "Error: Watcher 'Notes' key 'notify'" in err
    assert "requires the desktop-notifier package" in err


def test_check_reports_file_change_between_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that check saves a baseline, then shows what changed since the last run."""
    watched = tmp_path / "notes.txt"
    watched.write_text("initial contents\n", encoding="utf-8")
    config = _file_config(tmp_path, watched)

    assert main(["check", str(config)]) == 0
    assert "Notes: baseline saved" in capsys.readouterr().out

    assert main(["check", str(config)]) == 0
    assert "Notes: no changes" in capsys.readouterr().out

    watched.write_text("edited contents\n", encoding="utf-8")
    assert main(["check", str(config)]) == 0
    out = capsys.readouterr().out
    assert "-initial contents" in out
    assert "+edited contents" in out
    assert "Notes: 1 change(s) detected" in out


def test_check_without_database_starts_from_scratch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that without a database every check is a baseline."""
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")
    config = _file_config(tmp_path, watched, database=None)

    assert main(["check", str(config)]) == 0
    assert main(["check", str(config)]) == 0
    assert capsys.readouterr().out.count("Notes: baseline saved") == 2


def test_check_records_history(tmp_path: Path) -> None:
    """Test that every check is saved to the history in the config's database."""
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")
    config = _file_config(tmp_path, watched)

    main(["check", str(config)])
    main(["check", str(config)])

    checks = list(HistoryStore(tmp_path / "watchtower.db").checks())
    assert [(check.watcher_name, check.ok) for check in checks] == [("Notes", True)] * 2


def test_check_goes_on_after_a_failing_watcher(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that one broken watcher is reported and the next one still runs."""
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")
    config = _write_config(
        tmp_path,
        dedent(f"""
            watchers:
              - name: Missing
                source: {{ type: file, path: "{(tmp_path / "missing.txt").as_posix()}" }}
                diff: {{ type: text }}
              - name: Notes
                source: {{ type: file, path: "{watched.as_posix()}" }}
                diff: {{ type: text }}
            """),
    )

    assert main(["check", str(config)]) == 1
    captured = capsys.readouterr()
    assert "Error: Missing:" in captured.err
    assert "Notes: baseline saved" in captured.out


def test_missing_config_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a config file that does not exist gives an error, not a traceback."""
    assert main(["check", str(tmp_path / "missing.yaml")]) == 1
    assert capsys.readouterr().err.startswith("Error:")


def test_unusable_database_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that a database in a folder that does not exist gives an error message."""
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")
    config = _file_config(tmp_path, watched, database="missing/watchtower.db")

    assert main(["check", str(config)]) == 1
    assert capsys.readouterr().err.startswith("Error:")


def test_run_checks_until_ctrl_c(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that run starts the scheduler with logging and stops cleanly on Ctrl+C."""

    def run_once_then_ctrl_c(scheduler: Scheduler) -> None:
        """Run the due checks, then act as if the user pressed Ctrl+C."""
        scheduler.run_pending()
        raise KeyboardInterrupt

    monkeypatch.setattr(Scheduler, "run_forever", run_once_then_ctrl_c)
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")

    with caplog.at_level(logging.INFO):
        assert main(["run", str(_file_config(tmp_path, watched))]) == 0

    out = capsys.readouterr().out
    assert "Running 1 watcher(s)" in out
    assert "Stopped." in out
    assert "Checked 'Notes'" in caplog.text
    assert len(list(HistoryStore(tmp_path / "watchtower.db").checks())) == 1


def test_gui_starts_the_app_with_the_watchers_of_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that gui gives run_gui the scheduled watchers and the history, and returns its code."""
    started: list[tuple[Scheduler, HistoryStore | None]] = []

    def fake_run_gui(
        scheduler: Scheduler, event_bus: EventBus, history: HistoryStore | None
    ) -> int:
        """Remember what the app got instead of opening a window."""
        started.append((scheduler, history))
        return 3

    monkeypatch.setattr("watchtower.gui.run_gui", fake_run_gui)
    watched = tmp_path / "notes.txt"
    watched.write_text("contents\n", encoding="utf-8")

    assert main(["gui", str(_file_config(tmp_path, watched))]) == 3
    [(scheduler, history)] = started
    assert [status.name for status in scheduler.statuses()] == ["Notes"]
    assert history is not None


@pytest.mark.network
def test_check_reports_only_cheap_new_flats(
    tmp_path: Path, fake_listings: FakeListings, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the M3 demo: only a new flat under 3000 without an agency is reported."""
    config = _flats_config(tmp_path, fake_listings.base_url)
    assert main(["check", str(config)]) == 0
    assert "Cheap flats: baseline saved" in capsys.readouterr().out

    new_flats = [
        {"id": "3", "title": "Flat Krowodrza", "price": 2800, "description": ""},
        {"id": "4", "title": "Flat Podgorze", "price": 4200, "description": ""},
        {"id": "5", "title": "Agency flat", "price": 2000, "description": ""},
    ]
    fake_listings.write([*SAMPLE_LISTINGS, *new_flats])
    assert main(["check", str(config)]) == 0
    out = capsys.readouterr().out
    assert "Flat Krowodrza" in out
    assert "Flat Podgorze" not in out
    assert "Agency flat" not in out

    changes = list(HistoryStore(tmp_path / "watchtower.db").changes())
    assert [change.title for change in changes] == ["Flat Krowodrza"]


def test_check_server_down(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that an unreachable website gives an error naming the watcher."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
    config = _flats_config(tmp_path, f"http://127.0.0.1:{free_port}")

    assert main(["check", str(config)]) == 1
    assert "Error: Cheap flats:" in capsys.readouterr().err
