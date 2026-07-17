"""Function Length Bimodality metric — Pearson's bimodality coefficient (arch §2.2).

Shape statistic over the distribution of statement_count across module
functions. BC > 5/9 ≈ 0.555 flags "many short + a few long" bimodal patterns.

Formula (Pearson's moment coefficient):
  BC = (skewness² + 1) / (kurtosis + 3·(n-1)² / ((n-2)·(n-3)))
  where skewness = m3 / m2^1.5
        kurtosis = m4 / m2² - 3   (excess kurtosis)
        m_k = k-th central moment

Hand-rolled over stdlib `statistics` — avoids ~100MB scipy dep.

Confidence tiers (three-tier):
  n < 4: value=0.0, LOW, notes="n=<n> below minimum 4 for bimodality"
    (Pearson's denominator terms undefined for n-3 ≤ 0)
  4 ≤ n < 30: LOW, notes="n=<n> (below calibration min 30)"
  n ≥ 30: HIGH, notes="n=<n>"

Degenerate case: all values identical → m2 = 0 → return 0.0 with specific notes.

KNOWN GAPS (metric_version=1.0.0):
- Per-module bimodality; cross-file (package-level) aggregation deferred.
- Small-n bias: Pearson's BC at n<30 tends to undershoot the true asymptotic
  threshold; a bimodal fixture at n=8 may yield BC≈0.4 even when the
  distribution is visually bimodal. Calibration via n≥30 samples is authoritative.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)

MIN_VALID_N: int = 4
HIGH_CONFIDENCE_N: int = 30


def _bimodality_coefficient(samples: Sequence[int]) -> float:
    """Pearson's moment coefficient of bimodality. Returns 0.0 if undefined."""
    n = len(samples)
    if n < MIN_VALID_N:
        return 0.0
    mean = statistics.fmean(samples)
    m2 = sum((x - mean) ** 2 for x in samples) / n
    if m2 == 0:  # all values identical — bimodality undefined
        return 0.0
    m3 = sum((x - mean) ** 3 for x in samples) / n
    m4 = sum((x - mean) ** 4 for x in samples) / n
    skewness = m3 / (m2**1.5)
    kurtosis = m4 / (m2**2) - 3  # excess kurtosis
    denom = kurtosis + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    if denom == 0:  # defensive — shouldn't happen for n ≥ 4
        return 0.0
    return float((skewness**2 + 1) / denom)


class FunctionLengthBimodalityMetric:
    id: str = "function_length_bimodality"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.MODULE})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})
    shape_invariant: bool = True

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        fns = context.parse_result.functions
        n = len(fns)
        counts = [f.statement_count for f in fns]

        if n < MIN_VALID_N:
            return MetricValue(
                metric_id=self.id,
                value=0.0,
                metric_version=self.version,
                confidence=Confidence.LOW,
                notes=f"n={n} below minimum {MIN_VALID_N} for bimodality",
            )

        # Handle all-equal case explicitly so notes are meaningful.
        if len(set(counts)) == 1:
            return MetricValue(
                metric_id=self.id,
                value=0.0,
                metric_version=self.version,
                confidence=Confidence.LOW if n < HIGH_CONFIDENCE_N else Confidence.HIGH,
                notes=f"n={n}; all functions have identical length",
            )

        bc = _bimodality_coefficient(counts)

        if n < HIGH_CONFIDENCE_N:
            confidence = Confidence.LOW
            notes = f"n={n} (below calibration min {HIGH_CONFIDENCE_N})"
        else:
            confidence = Confidence.HIGH
            notes = f"n={n}"

        return MetricValue(
            metric_id=self.id,
            value=bc,
            metric_version=self.version,
            confidence=confidence,
            notes=notes,
        )


FUNCTION_LENGTH_BIMODALITY_METRIC = FunctionLengthBimodalityMetric()
