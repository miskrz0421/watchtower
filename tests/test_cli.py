"""Tests for the watchtower CLI."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from conftest import SAMPLE_LISTINGS, FakeListings
from watchtower.cli import main


def test_cli_check_demo(capsys: pytest.CaptureFixture[str]) -> None:
    """Test running watchtower check with no arguments executes M1 demo."""
    code = main(["check"])
    assert code == 0

    captured = capsys.readouterr()
    assert "Watchtower M1 Demo: Foundations" in captured.out
    assert "Flat in Krowodrza - 2800 PLN [NEW!]" in captured.out
    assert "Demo completed successfully" in captured.out


def test_cli_check_file_reports_change_between_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that check FILE --db saves a baseline, then shows what changed since."""
    target_file = tmp_path / "watch_me.txt"
    db = str(tmp_path / "watchtower.db")
    target_file.write_text("initial contents\n", encoding="utf-8")

    assert main(["check", str(target_file), "--db", db]) == 0
    assert "Baseline saved" in capsys.readouterr().out

    assert main(["check", str(target_file), "--db", db]) == 0
    assert "No changes" in capsys.readouterr().out

    target_file.write_text("edited contents\n", encoding="utf-8")
    assert main(["check", str(target_file), "--db", db]) == 0
    out = capsys.readouterr().out
    assert "-initial contents" in out
    assert "+edited contents" in out


def test_cli_check_file_without_db_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that checking a file without --db explains why it cannot work."""
    target_file = tmp_path / "watch_me.txt"
    target_file.write_text("initial contents\n", encoding="utf-8")

    assert main(["check", str(target_file)]) == 2
    assert "needs --db PATH" in capsys.readouterr().err


def test_cli_storage_error_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that an unusable database path gives an error message, not a traceback."""
    target_file = tmp_path / "watch_me.txt"
    target_file.write_text("initial contents\n", encoding="utf-8")
    db = str(tmp_path / "missing" / "watchtower.db")

    assert main(["check", str(target_file), "--db", db]) == 1
    assert "Error: Cannot open snapshot database" in capsys.readouterr().err


def test_cli_check_file_nonexistent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test running watchtower check with a nonexistent file path fails."""
    nonexistent = tmp_path / "does_not_exist.txt"
    code = main(["check", str(nonexistent)])
    assert code == 1

    captured = capsys.readouterr()
    assert "Error: File not found" in captured.err


def test_cli_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Test running watchtower without arguments prints help text."""
    code = main([])
    assert code == 0

    captured = capsys.readouterr()
    assert "usage: watchtower" in captured.out


@pytest.mark.network
def test_cli_check_db_reports_new_listing(
    tmp_path: Path, fake_listings: FakeListings, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the M2 demo: baseline, a new listing is reported, then no false alert."""
    url = f"{fake_listings.base_url}/listings"
    args = ["check", "--db", str(tmp_path / "watchtower.db"), "--url", url]

    assert main(args) == 0
    assert "Baseline saved for 'Krakow flats'" in capsys.readouterr().out

    new = {"id": "3", "title": "Flat Krowodrza", "price": 2800, "description": ""}
    fake_listings.write([*SAMPLE_LISTINGS, new])
    assert main(args) == 0
    assert "Flat Krowodrza" in capsys.readouterr().out

    assert main(args) == 0
    assert "No changes for 'Krakow flats'" in capsys.readouterr().out


def test_cli_check_db_server_down(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that an unreachable listings page gives an error message, not a traceback."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{free_port}/listings"

    assert main(["check", "--db", str(tmp_path / "watchtower.db"), "--url", url]) == 1
    assert "Error:" in capsys.readouterr().err
