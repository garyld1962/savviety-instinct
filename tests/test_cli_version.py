"""Tests for `instinct version`."""

from __future__ import annotations

from typer.testing import CliRunner

from savviety_instinct import __version__
from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.cli.app import app

runner = CliRunner()


def test_version_prints_tool_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_lists_every_registered_metric() -> None:
    result = runner.invoke(app, ["version"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "(none registered)" not in result.stdout
    for metric in METRICS_REGISTRY:
        assert f"  {metric.id}: {metric.version}" in result.stdout
