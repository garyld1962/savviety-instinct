"""Tests for analyze.pipeline — file walking + metric dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.pipeline import run_pipeline
from savviety_instinct.config.models import InstinctConfig
from tests._helpers import expected_row_count

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _cfg(**overrides) -> InstinctConfig:
    base: dict = dict(scope="personal", suppress=[])
    base.update(overrides)
    return InstinctConfig(**base)


def test_run_single_file_yields_expected_metrics() -> None:
    results, summary = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    results = list(results)
    # 10 functions × 6 metrics + 1 module × 1 metric = 61 rows (Slice 4b added trivial_delegation_ratio).
    assert len(results) == expected_row_count(n_functions=10, n_modules=1)
    assert summary.files_parsed == 1
    assert summary.files_skipped == 0
    assert summary.functions_analyzed == 10


def test_run_directory_walks_recursively() -> None:
    results, summary = run_pipeline(FIXTURES, _cfg())
    results = list(results)
    # FIXTURES contains multiple .py files. At least 61 rows from metric_fixtures.py.
    assert len(results) >= expected_row_count(n_functions=10, n_modules=1)
    assert summary.files_parsed >= 1


def test_suppression_skips_files() -> None:
    results, summary = run_pipeline(FIXTURES, _cfg(suppress=["**/metric_fixtures.py"]))
    files_seen = {r[0].source_range.file_path for r in results}
    assert not any("metric_fixtures.py" in f for f in files_seen)


def test_syntax_error_file_is_skipped_with_stderr_log(capsys) -> None:
    results, summary = run_pipeline(FIXTURES / "syntax_error.py", _cfg())
    list(results)  # drain
    captured = capsys.readouterr()
    assert "[parse-error]" in captured.err
    assert summary.files_skipped == 1
    assert summary.files_parsed == 0


def test_nonexistent_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        list(run_pipeline(Path("/nonexistent/path"), _cfg())[0])


def test_returns_deterministic_order() -> None:
    gen1, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    gen2, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    order1 = [(r[0].name, r[1].metric_id) for r in gen1]
    order2 = [(r[0].name, r[1].metric_id) for r in gen2]
    assert order1 == order2


def test_pipeline_summary_is_mutable_view() -> None:
    """Summary reflects counts after the iterator is drained."""
    results, summary = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    assert summary.files_parsed == 0  # pre-drain
    list(results)  # drain
    assert summary.files_parsed == 1  # post-drain
