"""Metric implementations (arch §5.3 pipeline stage 5)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics.cognitive import COGNITIVE_METRIC
from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
from savviety_instinct.analyze.metrics.identifier_quality import IDENTIFIER_QUALITY_METRIC
from savviety_instinct.analyze.metrics.max_nesting_depth import MAX_NESTING_DEPTH_METRIC
from savviety_instinct.analyze.metrics.median_function_length import (
    MEDIAN_FUNCTION_LENGTH_METRIC,
)
from savviety_instinct.analyze.metrics.npath import NPATH_METRIC
from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC
from savviety_instinct.analyze.metrics.trivial_delegation_ratio import (
    TRIVIAL_DELEGATION_RATIO_METRIC,
)

__all__ = [
    "COGNITIVE_METRIC",
    "CYCLOMATIC_METRIC",
    "IDENTIFIER_QUALITY_METRIC",
    "MAX_NESTING_DEPTH_METRIC",
    "MEDIAN_FUNCTION_LENGTH_METRIC",
    "NPATH_METRIC",
    "STATEMENT_COUNT_METRIC",
    "TRIVIAL_DELEGATION_RATIO_METRIC",
]
