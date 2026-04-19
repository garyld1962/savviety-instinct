"""Slice 4b integration — end-to-end pipeline emits module + function metrics."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.cli.app import app
from savviety_instinct.core.types import ArtifactKind
from tests._helpers import expected_row_count

FIXTURES = Path(__file__).parent.parent / "fixtures" / "python" / "modules"


def _write_config(cfg_dir: Path) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("scope: personal\nsuppress: []\n")


def test_cli_emits_module_and_function_rows(tmp_path, monkeypatch) -> None:
    """Running on a single module fixture emits:
    - N_functions × 6 function-metric rows
    - 1 module × 3 module-metric rows
    """
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    target = FIXTURES / "trivial_facade.py"
    result = runner.invoke(app, ["run", str(target)], catch_exceptions=False)
    assert result.exit_code == 0

    rows = [line for line in result.output.splitlines() if "\t" in line]
    from savviety_instinct.parse.python import PYTHON_ADAPTER

    parse_result = PYTHON_ADAPTER.parse_path(target)
    n_fns = len(parse_result.functions)
    assert len(rows) == expected_row_count(n_functions=n_fns, n_modules=1)


def test_registry_has_three_new_module_metrics() -> None:
    module_metric_ids = {m.id for m in METRICS_REGISTRY if ArtifactKind.MODULE in m.applies_to}
    assert module_metric_ids == {
        "trivial_delegation_ratio",
        "median_function_length",
        "function_length_bimodality",
    }


def test_empty_module_still_produces_module_rows(tmp_path, monkeypatch) -> None:
    """A .py file with zero functions produces exactly 3 module rows + 0 function rows."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES / "empty.py")], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.output.splitlines() if "\t" in line]
    assert len(rows) == expected_row_count(n_functions=0, n_modules=1)
    assert len(rows) == 3


def test_spot_check_bimodal_fixture_value(tmp_path, monkeypatch) -> None:
    """bimodal.py's function_length_bimodality metric value is > 0 and < 5/9 at n=8.

    At n=8, Pearson's formula has small-n attenuation — BC will be positive
    (some skew/shape signal) but below the catalog's 5/9 threshold. The
    threshold-crossing case is pinned by test_spot_check_large_sample_flags_bimodal
    below.
    """
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES / "bimodal.py")], catch_exceptions=False)
    assert result.exit_code == 0

    bimodality_line = None
    for line in result.output.splitlines():
        if "\t" in line and "function_length_bimodality" in line:
            bimodality_line = line
            break
    assert bimodality_line is not None, "expected function_length_bimodality row"
    # Row format is tab-separated. Find the part that starts with metric_id=value.
    parts = bimodality_line.split("\t")
    metric_part = next(p for p in parts if p.startswith("function_length_bimodality="))
    value_str = metric_part.split("=", 1)[1]
    value = float(value_str)
    assert 0.0 < value < 5 / 9, f"expected positive BC < 5/9 at n=8; got {value}"


def test_spot_check_large_sample_flags_bimodal(tmp_path, monkeypatch) -> None:
    """large_sample.py at n=32 yields BC > 5/9 — pins the catalog threshold case."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES / "large_sample.py")], catch_exceptions=False)
    assert result.exit_code == 0

    for line in result.output.splitlines():
        if "\t" in line and "function_length_bimodality" in line:
            parts = line.split("\t")
            metric_part = next(p for p in parts if p.startswith("function_length_bimodality="))
            value = float(metric_part.split("=", 1)[1])
            assert value > 5 / 9, f"expected BC > 5/9 at n>=30; got {value}"
            return
    raise AssertionError("expected function_length_bimodality row")
