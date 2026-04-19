"""Unit tests for max_nesting_depth metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.max_nesting_depth import MAX_NESTING_DEPTH_METRIC
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
        ("single_if", 1),
        ("single_if_with_boolean", 1),
        ("nested_if", 2),
        ("for_loop_only", 1),
        ("for_with_if", 2),
        ("try_except", 1),
        ("ternary", 0),
        ("comprehension", 0),
    ],
)
def test_max_nesting_matches_fixture(metric_fixtures_result, qualified, expected) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = MAX_NESTING_DEPTH_METRIC.compute(artifact, ctx)
    assert value.value == expected, f"{qualified}: expected {expected}, got {value.value}"


def test_max_nesting_metadata() -> None:
    assert MAX_NESTING_DEPTH_METRIC.id == "max_nesting_depth"
    assert MAX_NESTING_DEPTH_METRIC.version == "1.0.0"
    assert MAX_NESTING_DEPTH_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert MAX_NESTING_DEPTH_METRIC.required_inputs == frozenset({InputKind.AST})


def test_max_nesting_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert MAX_NESTING_DEPTH_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_max_nesting_raises_without_parse_result(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    with pytest.raises(ValueError, match="parse_result"):
        MAX_NESTING_DEPTH_METRIC.compute(artifact, AnalysisContext())
