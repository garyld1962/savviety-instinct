"""trivial_delegation_ratio metric tests (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.trivial_delegation_ratio import (
    TRIVIAL_DELEGATION_RATIO_METRIC,
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


def _module_artifact_and_ctx(path: Path):
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
    return artifact, ctx


def test_applies_to_module_only() -> None:
    assert TRIVIAL_DELEGATION_RATIO_METRIC.applies_to == frozenset({ArtifactKind.MODULE})


def test_trivial_facade_ratio() -> None:
    """trivial_facade.py: 5 trivial delegates out of 7 functions (includes helper)."""
    artifact, ctx = _module_artifact_and_ctx(MODULES / "trivial_facade.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.metric_id == "trivial_delegation_ratio"
    assert value.value == pytest.approx(5 / 7, abs=1e-6)
    assert value.confidence == Confidence.LOW  # n=7 < 20


def test_real_work_zero_ratio() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "real_work.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW  # n=5 < 20


def test_empty_module_sentinel() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "empty.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW
    assert value.notes == "no functions in module"


def test_single_fn_module() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "single.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW  # n=1 < 20


def test_at_threshold_medium_confidence() -> None:
    """at_threshold.py has 21 functions (≥20) — confidence bumps to MEDIUM; ratio=10/21."""
    artifact, ctx = _module_artifact_and_ctx(MODULES / "at_threshold.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.confidence == Confidence.MEDIUM
    assert value.value == pytest.approx(10 / 21, abs=1e-6)


def test_large_sample_medium_confidence() -> None:
    """large_sample.py has 32 functions — MEDIUM confidence (≥20)."""
    artifact, ctx = _module_artifact_and_ctx(MODULES / "large_sample.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.confidence == Confidence.MEDIUM
    assert value.value == pytest.approx(6 / 32, abs=1e-6)


def test_notes_report_sample_size() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "trivial_facade.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert "n=7" in (value.notes or "")
    assert "below min" in (value.notes or "")
