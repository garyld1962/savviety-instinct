"""Statement Count metric — count of executable statements per function.

Arch §1.5. Reads the pre-computed `FunctionDefNode.statement_count` value
from the parse layer (populated during Slice 3 Task 3). The metric itself
does no traversal; it's a pure lookup.
"""

from __future__ import annotations

from savviety_instinct.analyze.metrics._resolve import resolve_function_node
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)


class StatementCountMetric:
    id: str = "statement_count"
    version: str = "1.2.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        fn = resolve_function_node(self.id, artifact, context)
        return MetricValue(
            metric_id=self.id,
            value=fn.statement_count,
            metric_version=self.version,
            confidence=Confidence.HIGH,
        )


STATEMENT_COUNT_METRIC = StatementCountMetric()
