"""CliRunner tests for `instinct run`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.cli.app import app

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _write_config(cfg_dir: Path) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    # suppress: [] so fixture files under tests/ are not excluded by the
    # default suppress patterns (which include **/tests/**).
    (cfg_dir / "config.yaml").write_text("scope: personal\nsuppress: []\n")


def test_run_on_single_file_prints_rows(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # Lines with at least one tab are result rows (summary goes to stderr).
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    # 10 functions × 3 metrics = 30 rows
    assert len(rows) == 30
    for row in rows:
        cols = row.split("\t")
        assert len(cols) == 4, row
        assert ":" in cols[0] and "-" in cols[0]
        assert "=" in cols[2]


def test_run_on_directory_walks(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES)], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    assert len(rows) >= 30


def test_run_on_nonexistent_path_exits_nonzero(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", "/nonexistent/path"], catch_exceptions=False)
    assert result.exit_code != 0


def test_run_prints_summary_to_stderr(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    # mix_stderr is not supported in this Click version; stdout+stderr are mixed
    # into result.output. The [summary] line is written to stderr via err=True.
    runner = CliRunner()
    result = runner.invoke(
        app, ["run", str(FIXTURES / "metric_fixtures.py")], catch_exceptions=False
    )
    assert "[summary]" in result.output


def test_run_rows_are_deterministically_sorted(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result1 = runner.invoke(
        app, ["run", str(FIXTURES / "metric_fixtures.py")], catch_exceptions=False
    )
    result2 = runner.invoke(
        app, ["run", str(FIXTURES / "metric_fixtures.py")], catch_exceptions=False
    )
    rows1 = [line for line in result1.stdout.splitlines() if "\t" in line]
    rows2 = [line for line in result2.stdout.splitlines() if "\t" in line]
    assert rows1 == rows2
