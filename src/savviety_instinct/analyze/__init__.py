"""analyze/ — metric computation and pipeline orchestration (arch §5.3)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    STATEMENT_COUNT_METRIC,
)
from savviety_instinct.analyze.pipeline import PipelineSummary, run_pipeline
from savviety_instinct.analyze.rules import CognitiveRules, load_cognitive_rules

# Module-level registry. Ordered for deterministic output in CLI reports.
METRICS_REGISTRY = (
    STATEMENT_COUNT_METRIC,
    CYCLOMATIC_METRIC,
    COGNITIVE_METRIC,
)

__all__ = [
    "COGNITIVE_METRIC",
    "CYCLOMATIC_METRIC",
    "CognitiveRules",
    "METRICS_REGISTRY",
    "PipelineSummary",
    "STATEMENT_COUNT_METRIC",
    "load_cognitive_rules",
    "run_pipeline",
]
