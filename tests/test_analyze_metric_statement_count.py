"""Unit tests for the statement_count metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
    SourceRange,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent / "fixtures" / "python"


@pytest.fixture
def metric_fixtures_result():
    return PYTHON_ADAPTER.parse_path(FIXTURES / "metric_fixtures.py")


def _artifact_for(result, qualified_name: str) -> Artifact:
    fn = next(f for f in result.functions if f.qualified_name == qualified_name)
    return Artifact(
        ast_hash=fn.ast_hash,
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name=fn.name,
        enclosing_scope=fn.enclosing_class,
        source_range=fn.source_range,
    )


@pytest.mark.parametrize(
    "qualified,expected",
    [
        ("empty", 0),
        ("two_statements", 2),
        ("single_if", 3),
        ("single_if_with_boolean", 3),
        ("nested_if", 4),
        ("for_loop_only", 4),
        ("for_with_if", 5),
        ("try_except", 4),
        ("ternary", 1),
        ("comprehension", 1),
    ],
)
def test_statement_count_matches_fixture_annotation(
    metric_fixtures_result, qualified: str, expected: int
) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = STATEMENT_COUNT_METRIC.compute(artifact, ctx)
    assert value.value == expected, (
        f"{qualified}: expected {expected}, got {value.value}. "
        f"If the parse-layer statement_count algorithm changed, update the "
        f"fixture docstrings in lockstep."
    )


def test_statement_count_metric_metadata() -> None:
    assert STATEMENT_COUNT_METRIC.id == "statement_count"
    assert STATEMENT_COUNT_METRIC.version == "1.1.0"
    assert STATEMENT_COUNT_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert STATEMENT_COUNT_METRIC.required_inputs == frozenset({InputKind.AST})


def test_statement_count_returns_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = STATEMENT_COUNT_METRIC.compute(artifact, ctx)
    assert value.confidence == Confidence.HIGH


def test_statement_count_raises_without_parse_result(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    ctx = AnalysisContext()  # parse_result is None
    with pytest.raises(ValueError, match="parse_result"):
        STATEMENT_COUNT_METRIC.compute(artifact, ctx)


def test_statement_count_raises_when_artifact_not_found(metric_fixtures_result) -> None:
    """If the artifact's ast_hash doesn't match anything in parse_result.functions,
    the metric raises rather than silently returning 0.
    """
    artifact = Artifact(
        ast_hash="nonexistent_hash",
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name="missing",
        enclosing_scope=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=1),
    )
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    with pytest.raises(LookupError, match="ast_hash"):
        STATEMENT_COUNT_METRIC.compute(artifact, ctx)
