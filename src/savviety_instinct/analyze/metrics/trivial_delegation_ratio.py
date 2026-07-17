"""Trivial Delegation Ratio metric — ravioli-pattern signal (arch §2.1).

Module-scope. Counts the fraction of functions whose body is a trivial
wrapper for another call (RETURN_PASSTHROUGH, ASSIGN_DELEGATE, or
WRAPPER_NO_TRANSFORM). Triviality classification is pre-computed on
FunctionDefNode.delegation_kind in the parse layer.

Confidence tiers (per plan Scope Decision #10):
  n = 0: value=0.0, LOW, notes="no functions in module"
  0 < n < 20: LOW, notes="n=<n> (below min sample size 20)"
  n ≥ 20: MEDIUM, notes="n=<n>"

KNOWN GAPS (metric_version=1.0.0):
- R1 triviality detection is deliberately strict (exact passthrough only);
  super(), async, and attribute-call targets are missed. See
  parse.types.DelegationKind docstring for the full list.
- Catalog "facade by design" dismissal is an R2 concern — we do not
  distinguish intentional delegation from accidental ravioli at this layer.
"""

from __future__ import annotations

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)
from savviety_instinct.parse.types import DelegationKind

MIN_SAMPLE_SIZE: int = 20


class TrivialDelegationRatioMetric:
    id: str = "trivial_delegation_ratio"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.MODULE})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})
    # delegation_kind classification matches argument identifiers against
    # parameter names — identifier text ast_hash deliberately omits. Two
    # shape-identical modules can differ. Never cache by shape.
    shape_invariant: bool = False

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        fns = context.parse_result.functions
        n = len(fns)

        if n == 0:
            return MetricValue(
                metric_id=self.id,
                value=0.0,
                metric_version=self.version,
                confidence=Confidence.LOW,
                notes="no functions in module",
            )

        trivial = sum(1 for f in fns if f.delegation_kind != DelegationKind.NONE)
        ratio = trivial / n

        if n < MIN_SAMPLE_SIZE:
            confidence = Confidence.LOW
            notes = f"n={n} (below min sample size {MIN_SAMPLE_SIZE})"
        else:
            confidence = Confidence.MEDIUM
            notes = f"n={n}"

        return MetricValue(
            metric_id=self.id,
            value=ratio,
            metric_version=self.version,
            confidence=confidence,
            notes=notes,
        )


TRIVIAL_DELEGATION_RATIO_METRIC = TrivialDelegationRatioMetric()
