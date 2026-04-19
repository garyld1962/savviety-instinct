"""Statement Count metric — count of executable statements per function.

Arch §1.5. Reads the pre-computed `FunctionDefNode.statement_count` value
from the parse layer (populated during Slice 3 Task 3). The metric itself
does no traversal; it's a pure lookup.
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


class StatementCountMetric:
    id: str = "statement_count"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(
                f"{self.id} requires AnalysisContext.parse_result to be populated "
                "with the current file's ParseResult."
            )
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                return MetricValue(
                    metric_id=self.id,
                    value=fn.statement_count,
                    metric_version=self.version,
                    confidence=Confidence.HIGH,
                )
        raise LookupError(
            f"No FunctionDefNode with ast_hash={artifact.ast_hash!r} found in "
            f"parse_result.functions (file={context.parse_result.file_path!r})"
        )


STATEMENT_COUNT_METRIC = StatementCountMetric()
