"""Tests for `instinct init`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from savviety_instinct.cli.app import app

runner = CliRunner()


def _run_init_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["init", *args])


def test_init_creates_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.stdout
    config_path = tmp_path / ".instinct" / "config.yaml"
    assert config_path.exists()
    assert "scope: personal" in config_path.read_text()


def test_init_appends_gitignore_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".gitignore").write_text("# existing\n")
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".instinct/instinct.db" in gitignore
    assert ".instinct/reports/" in gitignore
    # Existing content preserved.
    assert "# existing" in gitignore


def test_init_creates_gitignore_if_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".instinct/instinct.db" in gitignore


def test_init_is_idempotent_on_gitignore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".gitignore").write_text(".instinct/instinct.db\n.instinct/reports/\n")
    # Remove config so init does its other work.
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0
    content = (tmp_path / ".gitignore").read_text()
    # Entries appear exactly once each.
    assert content.count(".instinct/instinct.db") == 1
    assert content.count(".instinct/reports/") == 1


def test_init_refuses_when_config_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".instinct").mkdir()
    (tmp_path / ".instinct" / "config.yaml").write_text("scope: personal\n")
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code != 0
    # Default CliRunner merges stderr into stdout; assert on stdout only.
    assert "exists" in result.stdout.lower()
