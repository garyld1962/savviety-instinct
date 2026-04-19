"""Unit tests for identifier_quality heuristic metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.identifier_quality import (
    IDENTIFIER_QUALITY_METRIC,
    STOPWORDS,
)
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
        ("empty", 1.0),
        ("two_statements", 1 / 3),
        ("single_if", 0.5),
        ("single_if_with_boolean", 1 / 3),
        ("nested_if", 0.5),
        ("for_loop_only", 1.0),
        ("for_with_if", 1.0),
        ("try_except", 2 / 3),
        ("ternary", 0.5),
        ("comprehension", 2 / 3),
    ],
)
def test_identifier_quality_matches_fixture(metric_fixtures_result, qualified, expected) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = IDENTIFIER_QUALITY_METRIC.compute(artifact, ctx)
    assert value.value == pytest.approx(expected, abs=0.001), (
        f"{qualified}: expected {expected:.3f}, got {value.value:.3f}"
    )


def test_identifier_quality_metadata() -> None:
    assert IDENTIFIER_QUALITY_METRIC.id == "identifier_quality"
    assert IDENTIFIER_QUALITY_METRIC.version == "1.0.0"
    assert IDENTIFIER_QUALITY_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert IDENTIFIER_QUALITY_METRIC.required_inputs == frozenset({InputKind.AST})


def test_identifier_quality_low_confidence(metric_fixtures_result) -> None:
    """Heuristic metrics return Confidence.LOW per arch §4.1."""
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = IDENTIFIER_QUALITY_METRIC.compute(artifact, ctx)
    assert value.confidence == Confidence.LOW


def test_stopwords_contents() -> None:
    """The stopword list is locked for Slice 4a; changes require a metric_version bump."""
    expected = {"i", "j", "k", "x", "y", "z", "tmp", "foo", "bar", "baz"}
    assert expected == STOPWORDS


def test_identifier_quality_raises_without_parse_result(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    with pytest.raises(ValueError, match="parse_result"):
        IDENTIFIER_QUALITY_METRIC.compute(artifact, AnalysisContext())
