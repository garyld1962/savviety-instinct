"""Tests for savviety_instinct.core.types (arch §5.1)."""

from __future__ import annotations

import pytest

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
    Metric,
    MetricValue,
    SourceRange,
)


def test_language_enum_has_mvp_languages():
    assert Language.PYTHON.value == "python"
    assert Language.RUST.value == "rust"
    assert Language.CSHARP.value == "csharp"
    assert Language.TYPESCRIPT.value == "typescript"


def test_artifact_kind_enum():
    assert {k.value for k in ArtifactKind} == {"function", "class", "module"}


def test_confidence_enum():
    assert {c.value for c in Confidence} == {"high", "medium", "low"}


def test_input_kind_enum_has_core_values():
    # InputKind is used by Metric.required_inputs. MVP metrics need at least
    # AST, call graph, and git history. Exact set can grow in later slices.
    values = {k.value for k in InputKind}
    assert {"ast", "call_graph", "git_history"}.issubset(values)


def test_source_range_is_frozen():
    r = SourceRange(file_path="x.py", line_start=1, line_end=10)
    with pytest.raises(Exception):
        r.file_path = "y.py"  # type: ignore[misc]


def test_artifact_is_frozen_and_carries_identity():
    a = Artifact(
        ast_hash="abc",
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name="foo",
        enclosing_scope=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=3),
    )
    assert a.ast_hash == "abc"
    with pytest.raises(Exception):
        a.ast_hash = "def"  # type: ignore[misc]


def test_metric_value_carries_confidence_and_version():
    mv = MetricValue(
        metric_id="cyclomatic_complexity",
        value=7,
        metric_version="0.0.0-slice1",
        confidence=Confidence.HIGH,
    )
    assert mv.confidence == Confidence.HIGH
    assert mv.notes is None


def test_analysis_context_is_constructible_with_defaults():
    ctx = AnalysisContext()
    # AnalysisContext is a forward-compat placeholder in Slice 1.
    # Slice 2+ will add call graph, imports, framework detection, etc.
    assert ctx is not None
    # Two default constructions are equal (frozen + no fields).
    assert AnalysisContext() == AnalysisContext()


def test_metric_protocol_runtime_checkable():
    class Dummy:
        id = "dummy"
        version = "0.0.0"
        applies_to: set[ArtifactKind] = {ArtifactKind.FUNCTION}
        required_inputs: set[InputKind] = {InputKind.AST}

        def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
            return MetricValue(
                metric_id=self.id,
                value=0,
                metric_version=self.version,
                confidence=Confidence.HIGH,
            )

    assert isinstance(Dummy(), Metric)
