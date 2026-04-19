"""Unit tests for npath metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.npath import NPATH_METRIC
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
        ("single_if", 3),
        ("single_if_with_boolean", 4),
        ("nested_if", 5),
        ("for_loop_only", 3),
        ("for_with_if", 5),
        ("try_except", 2),
        ("ternary", 3),
        ("comprehension", 3),
    ],
)
def test_npath_matches_fixture(metric_fixtures_result, qualified, expected) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = NPATH_METRIC.compute(artifact, ctx)
    assert value.value == expected, f"{qualified}: expected {expected}, got {value.value}"


def test_npath_metadata() -> None:
    assert NPATH_METRIC.id == "npath"
    assert NPATH_METRIC.version == "1.0.0"
    assert NPATH_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert NPATH_METRIC.required_inputs == frozenset({InputKind.AST})


def test_npath_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert NPATH_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_npath_empty_is_one(metric_fixtures_result) -> None:
    """NPATH of a trivial function body = 1 (base case)."""
    artifact = _artifact_for(metric_fixtures_result, "empty")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert NPATH_METRIC.compute(artifact, ctx).value == 1


def test_npath_raises_without_parse_result(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    with pytest.raises(ValueError, match="parse_result"):
        NPATH_METRIC.compute(artifact, AnalysisContext())
