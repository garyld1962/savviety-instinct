"""Integration: instinct run <fixtures> produces expected rows."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.cli.app import app
from tests._helpers import expected_row_count

FIXTURES = Path(__file__).parent.parent / "fixtures" / "python"


def _write_config(cfg_dir: Path) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    # Empty suppress list — don't filter fixtures/
    (cfg_dir / "config.yaml").write_text("scope: personal\nsuppress: []\n")


def test_end_to_end_on_metric_fixtures(tmp_path, monkeypatch) -> None:
    """Slice 3 acceptance: run on metric_fixtures.py, verify shape + spot-check."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    rows = [line.split("\t") for line in result.output.splitlines() if "\t" in line]
    assert len(rows) == expected_row_count(
        n_functions=10, n_modules=0
    )  # 10 functions × 6 metrics (Slice 4a expanded the registry)

    # Spot check: empty function has cognitive=0, cyclomatic=1, statement_count=0
    empty_rows = [r for r in rows if r[1] == "empty"]
    assert len(empty_rows) == 6  # 6 metrics per function post-Slice-4a
    metric_to_value = {r[2].split("=")[0]: r[2].split("=")[1] for r in empty_rows}
    assert metric_to_value["cognitive_complexity"] == "0"
    assert metric_to_value["cyclomatic_complexity"] == "1"
    assert metric_to_value["statement_count"] == "0"

    # Summary present
    assert "[summary]" in result.output
    assert "10 functions analyzed" in result.output


def test_end_to_end_on_directory_with_syntax_error(tmp_path, monkeypatch) -> None:
    """Parse errors degrade gracefully: syntax_error.py skipped, rest succeed."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES)], catch_exceptions=False)
    # Soft failures don't abort
    assert result.exit_code == 0
    assert "[parse-error]" in result.output
    assert "syntax_error.py" in result.output


def test_spot_check_single_if_with_boolean(tmp_path, monkeypatch) -> None:
    """Cognitive=2, cyclomatic=3, statement_count=3 per fixture docstring."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    rows = [line.split("\t") for line in result.output.splitlines() if "\t" in line]
    target = {
        r[2].split("=")[0]: r[2].split("=")[1] for r in rows if r[1] == "single_if_with_boolean"
    }
    assert target["cognitive_complexity"] == "2"
    assert target["cyclomatic_complexity"] == "3"
    assert target["statement_count"] == "3"
