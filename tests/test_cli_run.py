"""CliRunner tests for `instinct run`."""

from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.cli.app import app
from tests._helpers import expected_row_count

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
    # 10 functions × 6 metrics + 1 module × 1 metric = 61 rows (Slice 4b added trivial_delegation_ratio)
    assert len(rows) == expected_row_count(n_functions=10, n_modules=1)
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
    assert len(rows) >= expected_row_count(n_functions=10, n_modules=1)


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


def test_run_without_path_analyzes_current_directory(tmp_path, monkeypatch) -> None:
    """README documents `uv run instinct run` with no argument (README.md:52)."""
    _write_config(tmp_path / ".instinct")
    shutil.copy(FIXTURES / "metric_fixtures.py", tmp_path / "metric_fixtures.py")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run"], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    assert len(rows) == expected_row_count(n_functions=10, n_modules=1)


def test_run_dot_skips_venv_under_default_suppressions(tmp_path, monkeypatch) -> None:
    """`instinct run .` on this repo printed 230k rows from .venv/ (2026-09-03 review)."""
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")  # default suppress list
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def real(x):\n    return x + 1\n")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "junk.py").write_text("def junk(y):\n    return y\n")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", "."], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    assert rows, "expected metric rows for pkg/mod.py"
    assert all(".venv/" not in row for row in rows), rows
    assert any("pkg/mod.py" in row for row in rows)
