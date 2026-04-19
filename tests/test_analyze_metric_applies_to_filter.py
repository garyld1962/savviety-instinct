"""Pipeline honors Metric.applies_to; registry guards empty applies_to."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.analyze.pipeline import run_pipeline
from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import ArtifactKind

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _cfg() -> InstinctConfig:
    return InstinctConfig(scope="personal", suppress=[])


def test_function_metrics_only_fire_on_function_artifacts() -> None:
    """Every emitted metric_id that applies_to FUNCTION came from a FUNCTION artifact."""
    results, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    rows = list(results)

    fn_metric_ids = {m.id for m in METRICS_REGISTRY if ArtifactKind.FUNCTION in m.applies_to}
    for artifact, value in rows:
        if value.metric_id in fn_metric_ids:
            assert artifact.kind == ArtifactKind.FUNCTION, (
                f"{value.metric_id} fired on artifact.kind={artifact.kind}"
            )


def test_every_metric_has_nonempty_applies_to() -> None:
    """Guard documented in analyze/__init__.py — mirror it at test level."""
    for metric in METRICS_REGISTRY:
        assert metric.applies_to, f"{metric.id} has empty applies_to (silent-noop footgun)"
