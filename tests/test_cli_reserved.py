"""Tests for reserved R2+ command stubs (arch §7)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from savviety_instinct.cli.app import app

runner = CliRunner()

RESERVED_COMMANDS = ["sync", "curate", "suggest", "apply", "serve"]


@pytest.mark.parametrize("cmd", RESERVED_COMMANDS)
def test_reserved_command_exits_nonzero_with_message(cmd: str):
    result = runner.invoke(app, [cmd])
    assert result.exit_code == 2, f"{cmd} returned exit code {result.exit_code}"
    # Default CliRunner merges stderr into stdout; assert on stdout only.
    assert "not available" in result.stdout.lower()
