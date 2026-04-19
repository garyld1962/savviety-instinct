"""function_length_bimodality metric tests (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.analyze.metrics.function_length_bimodality import (
    FUNCTION_LENGTH_BIMODALITY_METRIC,
    _bimodality_coefficient,
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

# Threshold from catalog §2.2: BC > 0.555 flags bimodal. Only observable at n≥30+
# due to Pearson's small-n bias; we verify this via large_sample.py.
BIMODAL_THRESHOLD = 5 / 9


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
    return FUNCTION_LENGTH_BIMODALITY_METRIC.compute(artifact, ctx)


# ---------- Direct _bimodality_coefficient tests ----------


def test_bc_uniform_distribution_identical_values_is_zero() -> None:
    """All-equal samples → m2=0 (degenerate). Return 0.0."""
    assert _bimodality_coefficient([5, 5, 5, 5, 5, 5]) == 0.0


def test_bc_bimodal_at_high_n_exceeds_threshold() -> None:
    """Large bimodal sample at n≥30: 15 small + 15 large → BC > 5/9."""
    samples = [2] * 15 + [30] * 15
    assert _bimodality_coefficient(samples) > BIMODAL_THRESHOLD


def test_bc_near_normal_below_threshold() -> None:
    """Roughly-normal distribution → BC significantly below threshold."""
    samples = [5, 6, 7, 7, 8, 8, 8, 9, 9, 10, 10, 10, 10, 11, 11, 12, 12, 13, 14, 15]
    assert _bimodality_coefficient(samples) < BIMODAL_THRESHOLD


def test_bc_handles_smallest_valid_sample() -> None:
    """n=4 is the smallest n for which the formula's denominator is defined."""
    value = _bimodality_coefficient([1, 2, 3, 10])
    assert 0.0 <= value <= 1.0


# ---------- Metric-level tests ----------


def test_applies_to_module_only() -> None:
    assert FUNCTION_LENGTH_BIMODALITY_METRIC.applies_to == frozenset({ArtifactKind.MODULE})


def test_empty_module_sentinel() -> None:
    value = _compute(MODULES / "empty.py")
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW
    assert "n=0" in (value.notes or "")
    assert "below minimum 4" in (value.notes or "")


def test_single_fn_below_min_n() -> None:
    value = _compute(MODULES / "single.py")
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW
    assert "below minimum 4" in (value.notes or "")


def test_uniform_degenerate() -> None:
    value = _compute(MODULES / "uniform.py")
    assert value.value == 0.0
    assert "identical" in (value.notes or "")


def test_bimodal_fixture_exceeds_uniform() -> None:
    """bimodal.py BC > uniform.py BC (0.0). Small-n attenuation means we
    can't assert > 5/9 here; that's pinned by large_sample.py."""
    bimodal_value = _compute(MODULES / "bimodal.py")
    uniform_value = _compute(MODULES / "uniform.py")
    assert bimodal_value.value > uniform_value.value


def test_confidence_tier_below_30() -> None:
    """n=8 is in the 4≤n<30 tier — LOW confidence."""
    value = _compute(MODULES / "bimodal.py")
    assert value.confidence == Confidence.LOW


def test_confidence_tier_at_high_threshold() -> None:
    """large_sample.py has n=32 — HIGH confidence."""
    value = _compute(MODULES / "large_sample.py")
    assert value.confidence == Confidence.HIGH


def test_large_sample_bimodal_exceeds_catalog_threshold() -> None:
    """large_sample.py at n=32 yields BC > 5/9 (via skew/outlier pattern)."""
    value = _compute(MODULES / "large_sample.py")
    assert value.value > BIMODAL_THRESHOLD
