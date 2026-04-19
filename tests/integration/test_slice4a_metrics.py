"""Slice 4a integration: end-to-end CLI emits all six metrics per function."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.cli.app import app
from tests._helpers import expected_row_count

FIXTURES = Path(__file__).parent.parent / "fixtures" / "python"


def _write_config(cfg_dir: Path) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("scope: personal\nsuppress: []\n")


def test_cli_emits_six_metrics_per_function(tmp_path, monkeypatch) -> None:
    """60 rows = 10 functions × 6 metrics (Slice 3 trio + Slice 4a trio)."""
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
    assert len(rows) == expected_row_count(n_functions=10, n_modules=0)

    metric_ids = {r[2].split("=")[0] for r in rows}
    assert metric_ids == {
        "statement_count",
        "cyclomatic_complexity",
        "cognitive_complexity",
        "max_nesting_depth",
        "npath",
        "identifier_quality",
    }


def test_spot_check_nested_if_new_metrics(tmp_path, monkeypatch) -> None:
    """Verify max_nesting=2, npath=5, identifier_quality=0.5 for nested_if fixture."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    rows = [line.split("\t") for line in result.output.splitlines() if "\t" in line]
    target = {r[2].split("=")[0]: r[2].split("=")[1] for r in rows if r[1] == "nested_if"}
    assert target["max_nesting_depth"] == "2"
    assert target["npath"] == "5"
    assert target["identifier_quality"] == "0.5"


def test_identifier_quality_shows_low_confidence(tmp_path, monkeypatch) -> None:
    """identifier_quality rows emit confidence=low per arch §4.1."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    rows = [line.split("\t") for line in result.output.splitlines() if "\t" in line]
    iq_rows = [r for r in rows if r[2].startswith("identifier_quality=")]
    assert len(iq_rows) == 10
    for row in iq_rows:
        assert row[3] == "low", f"expected low confidence, got {row[3]}: {row}"
