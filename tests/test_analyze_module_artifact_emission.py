"""Pipeline emits one MODULE artifact per parsed file (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.analyze.pipeline import run_pipeline
from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import ArtifactKind, Language

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _cfg() -> InstinctConfig:
    return InstinctConfig(scope="personal", suppress=[])


def test_exactly_one_module_artifact_per_parsed_file() -> None:
    results, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    artifacts = {(r[0].kind, r[0].ast_hash) for r in results}
    module_artifacts = [a for a in artifacts if a[0] == ArtifactKind.MODULE]
    # With zero MODULE metrics in the registry yet, the module artifact appears
    # in the dedup'd set only if any metric emitted for it. Expected: zero.
    # Once Task 6 adds the first MODULE metric, this becomes == 1.
    assert len(module_artifacts) == 0


def test_module_artifact_fields_when_metric_emits(monkeypatch) -> None:
    """Directly verify the MODULE artifact shape by installing a stub metric.

    Avoids the Task 3 no-op (zero module metrics) by registering a
    transient stub that applies_to MODULE.
    """
    from savviety_instinct.core.types import (
        AnalysisContext,
        Artifact,
        Confidence,
        InputKind,
        MetricValue,
    )

    class _StubModuleMetric:
        id = "stub_module_metric"
        version = "0.0.0"
        applies_to = frozenset({ArtifactKind.MODULE})
        required_inputs = frozenset({InputKind.AST})

        def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
            return MetricValue(
                metric_id=self.id,
                value=artifact.source_range.line_end,
                metric_version=self.version,
                confidence=Confidence.HIGH,
            )

    import savviety_instinct.analyze as analyze_pkg

    patched_registry = (*analyze_pkg.METRICS_REGISTRY, _StubModuleMetric())
    monkeypatch.setattr(analyze_pkg, "METRICS_REGISTRY", patched_registry)

    results, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    rows = list(results)
    module_rows = [r for r in rows if r[0].kind == ArtifactKind.MODULE]

    assert len(module_rows) == 1
    artifact, value = module_rows[0]
    assert artifact.kind == ArtifactKind.MODULE
    assert artifact.language == Language.PYTHON
    assert artifact.name.endswith("metric_fixtures.py")
    assert artifact.enclosing_scope is None
    assert artifact.source_range.line_start == 1
    assert artifact.source_range.line_end >= 1
    assert artifact.ast_hash  # non-empty
    assert value.metric_id == "stub_module_metric"


def test_empty_module_still_emits_module_artifact(monkeypatch, tmp_path) -> None:
    """A .py file with zero functions still produces a MODULE artifact."""
    empty_file = tmp_path / "empty.py"
    empty_file.write_text('"""module docstring, no functions."""\n')

    from savviety_instinct.core.types import (
        AnalysisContext,
        Artifact,
        Confidence,
        InputKind,
        MetricValue,
    )

    class _StubModuleMetric:
        id = "stub_module_metric"
        version = "0.0.0"
        applies_to = frozenset({ArtifactKind.MODULE})
        required_inputs = frozenset({InputKind.AST})

        def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
            return MetricValue(
                metric_id=self.id,
                value=0,
                metric_version=self.version,
                confidence=Confidence.LOW,
            )

    import savviety_instinct.analyze as analyze_pkg

    monkeypatch.setattr(
        analyze_pkg, "METRICS_REGISTRY", (*analyze_pkg.METRICS_REGISTRY, _StubModuleMetric())
    )

    results, _ = run_pipeline(empty_file, _cfg())
    rows = list(results)
    module_rows = [r for r in rows if r[0].kind == ArtifactKind.MODULE]
    assert len(module_rows) == 1  # empty module still emits
