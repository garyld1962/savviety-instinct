"""median_function_length metric tests (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.analyze.metrics.median_function_length import (
    MEDIAN_FUNCTION_LENGTH_METRIC,
)
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    SourceRange,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

MODULES = Path(__file__).parent / "fixtures" / "python" / "modules"


def _compute(path: Path):
    result = PYTHON_ADAPTER.parse_path(path)
    artifact = Artifact(
        ast_hash="test",
        language=Language.PYTHON,
        kind=ArtifactKind.MODULE,
        name=str(path),
        enclosing_scope=None,
        source_range=SourceRange(file_path=str(path), line_start=1, line_end=1),
    )
    ctx = AnalysisContext(parse_result=result)
    return MEDIAN_FUNCTION_LENGTH_METRIC.compute(artifact, ctx), result


def test_applies_to_module_only() -> None:
    assert MEDIAN_FUNCTION_LENGTH_METRIC.applies_to == frozenset({ArtifactKind.MODULE})


def test_value_is_int() -> None:
    value, _ = _compute(MODULES / "uniform.py")
    assert isinstance(value.value, int)


def test_empty_module_sentinel() -> None:
    value, _ = _compute(MODULES / "empty.py")
    assert value.value == 0
    assert value.confidence == Confidence.LOW
    assert value.notes == "no functions in module"


def test_uniform_module_high_confidence() -> None:
    value, result = _compute(MODULES / "uniform.py")
    # All functions should have the same statement_count
    counts = [fn.statement_count for fn in result.functions]
    assert len(set(counts)) == 1
    assert value.value == counts[0]
    assert value.confidence == Confidence.HIGH  # n=10


def test_single_fn_low_confidence() -> None:
    value, _ = _compute(MODULES / "single.py")
    assert value.confidence == Confidence.LOW  # n=1 < 10


def test_matches_python_statistics_median() -> None:
    """Parity check: result matches int(statistics.median(...))."""
    import statistics

    value, result = _compute(MODULES / "real_work.py")
    counts = [fn.statement_count for fn in result.functions]
    expected = int(statistics.median(counts))
    assert value.value == expected
