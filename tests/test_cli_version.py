"""Tests for `instinct version`."""

from __future__ import annotations

from typer.testing import CliRunner

from savviety_instinct import __version__
from savviety_instinct.cli.app import app

runner = CliRunner()


def test_version_prints_tool_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_mentions_metrics_section():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    # In Slice 1 no metrics are registered; version should still list a
    # metrics section so the output shape is stable as metrics land.
    assert "metric" in result.stdout.lower()
