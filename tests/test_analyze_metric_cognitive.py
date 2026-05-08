"""Unit tests for the cognitive_complexity metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.cognitive import COGNITIVE_METRIC
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
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
        ("two_statements", 0),
        ("single_if", 1),  # if +1
        ("single_if_with_boolean", 2),  # if +1, bool_sequence +1
        ("nested_if", 3),  # outer if +1, inner if +1+1(nesting)=2 → total 3
        ("for_loop_only", 1),  # for +1
        ("for_with_if", 3),  # for +1, nested if +1+1(nesting)=2 → total 3
        ("try_except", 1),  # try +0 (nests), except +1 at depth 0 (sibling) → total 1
        ("ternary", 1),  # ternary +1
        ("comprehension", 1),  # comprehension +1
    ],
)
def test_cognitive_matches_fixture(metric_fixtures_result, qualified: str, expected: int) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = COGNITIVE_METRIC.compute(artifact, ctx)
    assert value.value == expected, f"{qualified}: expected {expected}, got {value.value}"


def test_cognitive_metadata() -> None:
    assert COGNITIVE_METRIC.id == "cognitive_complexity"
    assert COGNITIVE_METRIC.version == "1.1.0"
    assert COGNITIVE_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert COGNITIVE_METRIC.required_inputs == frozenset({InputKind.AST})


def test_cognitive_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert COGNITIVE_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_cognitive_minimum_is_zero(metric_fixtures_result) -> None:
    """Unlike cyclomatic (min 1), cognitive starts at 0 for straight-line code."""
    artifact = _artifact_for(metric_fixtures_result, "two_statements")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert COGNITIVE_METRIC.compute(artifact, ctx).value == 0


def test_cognitive_raises_without_parse_result(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    ctx = AnalysisContext()
    with pytest.raises(ValueError, match="parse_result"):
        COGNITIVE_METRIC.compute(artifact, ctx)
