"""Tests for the watchtower CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchtower.cli import main


def test_cli_check_demo(capsys: pytest.CaptureFixture[str]) -> None:
    """Test running watchtower check with no arguments executes M1 demo."""
    code = main(["check"])
    assert code == 0

    captured = capsys.readouterr()
    assert "Watchtower M1 Demo: Foundations" in captured.out
    assert "Flat in Krowodrza - 2800 PLN [NEW!]" in captured.out
    assert "Demo completed successfully" in captured.out


def test_cli_check_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test running watchtower check with a file path."""
    target_file = tmp_path / "watch_me.txt"
    target_file.write_text("initial contents\n", encoding="utf-8")

    code = main(["check", str(target_file)])
    assert code == 0


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
