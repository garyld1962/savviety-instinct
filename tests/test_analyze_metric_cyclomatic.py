"""Unit tests for the cyclomatic_complexity metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
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
        ("empty", 1),
        ("two_statements", 1),
        ("single_if", 2),
        ("single_if_with_boolean", 3),  # if +1, bool group +1 → 2+1=3
        ("nested_if", 3),  # 1 + outer if + inner if = 3
        ("for_loop_only", 2),  # 1 + for = 2
        ("for_with_if", 3),  # 1 + for + if = 3
        ("try_except", 2),  # 1 + except (try is wrapper) = 2
        ("ternary", 2),  # 1 + ternary = 2
        ("comprehension", 2),  # 1 + comprehension = 2
    ],
)
def test_cyclomatic_matches_fixture(metric_fixtures_result, qualified: str, expected: int) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = CYCLOMATIC_METRIC.compute(artifact, ctx)
    assert value.value == expected, f"{qualified}: expected {expected}, got {value.value}."


def test_cyclomatic_metadata() -> None:
    assert CYCLOMATIC_METRIC.id == "cyclomatic_complexity"
    assert CYCLOMATIC_METRIC.version == "1.0.0"
    assert CYCLOMATIC_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert CYCLOMATIC_METRIC.required_inputs == frozenset({InputKind.AST})


def test_cyclomatic_high_confidence_on_plain_python(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert CYCLOMATIC_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_cyclomatic_minimum_is_one(metric_fixtures_result) -> None:
    """M = decisions + 1; a function with zero decisions scores 1, not 0."""
    artifact = _artifact_for(metric_fixtures_result, "empty")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert CYCLOMATIC_METRIC.compute(artifact, ctx).value == 1


def test_cyclomatic_raises_without_parse_result(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    ctx = AnalysisContext()
    with pytest.raises(ValueError, match="parse_result"):
        CYCLOMATIC_METRIC.compute(artifact, ctx)
