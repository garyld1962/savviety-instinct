"""Cyclomatic Complexity (McCabe) metric.

Arch §1.1. Formula: M = decisions + 1.
Decisions count: if, elif, for, while, except, ternary, boolean sequence
(per group for Slice 3 — approximation), comprehension (per comprehension
for Slice 3 — approximation).

Confidence: high on plain Python with the standard decision set.

KNOWN GAP (metric_version=1.0.0):
- BOOLEAN_SEQUENCE counts +1 per group, NOT per operator. Arch §1.1 requires
  +1 per boolean operator (each `and`/`or`). Slice 3 ControlFlowNode does not
  carry operator count; adding it is a coordinated parse-layer bump.
- COMPREHENSION counts +1 per comprehension, NOT per generator/if clause.
  Same rationale.

Both gaps are documented in arch §1.1 pitfalls and tolerable because
cyclomatic is de-emphasized in favor of cognitive_complexity per §1.1 notes.
Fix in a later metric_version bump with finer-grained ControlFlowNode fields.
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
from savviety_instinct.parse.types import ControlFlowNode, ControlFlowNodeKind

# Kinds that contribute to the decision count.
_DECISION_KINDS: frozenset[ControlFlowNodeKind] = frozenset(
    {
        ControlFlowNodeKind.IF,
        ControlFlowNodeKind.ELIF,
        ControlFlowNodeKind.FOR,
        ControlFlowNodeKind.WHILE,
        ControlFlowNodeKind.EXCEPT,
        ControlFlowNodeKind.CASE,  # 1.1.0: each match case arm is a decision (Bug B1 fix)
        ControlFlowNodeKind.TERNARY,
        ControlFlowNodeKind.BOOLEAN_SEQUENCE,  # +1 per group — see module docstring
        ControlFlowNodeKind.COMPREHENSION,  # +1 per comprehension — see module docstring
    }
)


def _count_decisions(nodes: tuple[ControlFlowNode, ...]) -> int:
    count = 0
    for node in nodes:
        if node.kind in _DECISION_KINDS:
            count += 1
        count += _count_decisions(node.children)
    return count


class CyclomaticMetric:
    id: str = "cyclomatic_complexity"
    version: str = "1.2.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result to be populated.")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                value = _count_decisions(fn.control_flow) + 1
                return MetricValue(
                    metric_id=self.id,
                    value=value,
                    metric_version=self.version,
                    confidence=Confidence.HIGH,
                )
        raise LookupError(
            f"No FunctionDefNode with ast_hash={artifact.ast_hash!r} found in "
            f"parse_result.functions (file={context.parse_result.file_path!r})"
        )


CYCLOMATIC_METRIC = CyclomaticMetric()
