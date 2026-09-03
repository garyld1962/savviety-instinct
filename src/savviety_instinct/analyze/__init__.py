"""analyze/ — metric computation and pipeline orchestration (arch §5.3)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    FUNCTION_LENGTH_BIMODALITY_METRIC,
    IDENTIFIER_QUALITY_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    MEDIAN_FUNCTION_LENGTH_METRIC,
    NPATH_METRIC,
    STATEMENT_COUNT_METRIC,
    TRIVIAL_DELEGATION_RATIO_METRIC,
)
from savviety_instinct.analyze.persistence import run_pipeline_with_persistence
from savviety_instinct.analyze.pipeline import PipelineSummary, run_pipeline
from savviety_instinct.analyze.rules import CognitiveRules, load_cognitive_rules
from savviety_instinct.core.types import Metric

# Module-level registry. Ordered for deterministic output in CLI reports.
# Control-flow family first (statement_count sets up size-family too), then
# identifier_quality as a comprehensibility signal.
METRICS_REGISTRY: tuple[Metric, ...] = (
    # Function-level (Slice 3 + 4a)
    STATEMENT_COUNT_METRIC,
    CYCLOMATIC_METRIC,
    COGNITIVE_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    NPATH_METRIC,
    IDENTIFIER_QUALITY_METRIC,
    # Module-level (Slice 4b)
    TRIVIAL_DELEGATION_RATIO_METRIC,
    MEDIAN_FUNCTION_LENGTH_METRIC,
    FUNCTION_LENGTH_BIMODALITY_METRIC,
)

__all__ = [
    "COGNITIVE_METRIC",
    "CYCLOMATIC_METRIC",
    "CognitiveRules",
    "FUNCTION_LENGTH_BIMODALITY_METRIC",
    "IDENTIFIER_QUALITY_METRIC",
    "MAX_NESTING_DEPTH_METRIC",
    "MEDIAN_FUNCTION_LENGTH_METRIC",
    "METRICS_REGISTRY",
    "NPATH_METRIC",
    "PipelineSummary",
    "STATEMENT_COUNT_METRIC",
    "TRIVIAL_DELEGATION_RATIO_METRIC",
    "load_cognitive_rules",
    "run_pipeline",
    "run_pipeline_with_persistence",
]

# Slice 4b: fail-fast on a metric with empty applies_to. An empty frozenset
# means the pipeline filter silently drops the metric from all artifacts —
# no exception, no test failure unless the metric-specific test catches it.
# Asserting here is cheap (module-load time) and catches the footgun at its
# source.
assert all(m.applies_to for m in METRICS_REGISTRY), (
    "every Metric must declare at least one ArtifactKind in applies_to; "
    "an empty frozenset means the pipeline filter will drop it silently"
)
