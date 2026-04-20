"""Median Function Length metric (arch §2.2).

Module-scope. Median of `statement_count` across all functions in the module.
Catalog also describes a bimodality coefficient — that ships as a separate
metric (function_length_bimodality) per Slice 4b design spec §5.

Confidence tiers:
  n = 0: value=0, LOW, notes="no functions in module"
  0 < n < 10: LOW, notes="n=<n> (below min sample size 10)"
  n ≥ 10: HIGH, notes="n=<n>"

KNOWN GAPS (metric_version=1.0.0):
- Even-count modules truncate via int() cast ([2, 5] → median 3.5 → int 3).
  Matches catalog "integer (median)" surface but loses precision. Fix via
  metric_version bump if calibration shows the truncation mis-ranks modules.
"""

from __future__ import annotations

import statistics

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)

MIN_SAMPLE_SIZE: int = 10


class MedianFunctionLengthMetric:
    id: str = "median_function_length"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.MODULE})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        fns = context.parse_result.functions
        n = len(fns)

        if n == 0:
            return MetricValue(
                metric_id=self.id,
                value=0,
                metric_version=self.version,
                confidence=Confidence.LOW,
                notes="no functions in module",
            )

        median_value = int(statistics.median(f.statement_count for f in fns))

        if n < MIN_SAMPLE_SIZE:
            confidence = Confidence.LOW
            notes = f"n={n} (below min sample size {MIN_SAMPLE_SIZE})"
        else:
            confidence = Confidence.HIGH
            notes = f"n={n}"

        return MetricValue(
            metric_id=self.id,
            value=median_value,
            metric_version=self.version,
            confidence=confidence,
            notes=notes,
        )


MEDIAN_FUNCTION_LENGTH_METRIC = MedianFunctionLengthMetric()
