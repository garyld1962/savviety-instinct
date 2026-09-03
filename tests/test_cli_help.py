"""`--help` must render on the root app and on `run`.

Regression: typer 0.12.5 with click 8.3.2 raised
`TypeError: Parameter.make_metavar() missing 1 required positional argument: 'ctx'`
on every --help invocation. No earlier test exercised --help.
"""

from __future__ import annotations

from typer.testing import CliRunner

from savviety_instinct.cli.app import app

runner = CliRunner()


def test_root_help_renders_and_lists_commands() -> None:
    result = runner.invoke(app, ["--help"], catch_exceptions=False)
    assert result.exit_code == 0
    for cmd in ("version", "init", "run"):
        assert cmd in result.stdout


def test_run_help_renders() -> None:
    result = runner.invoke(app, ["run", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "--help" in result.stdout
