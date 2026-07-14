"""Maximum Nesting Depth metric (arch §1.4).

Walks the ControlFlowNode tree counting deepest nesting of block-level
control structures only. Expression-level CFNs (TERNARY,
BOOLEAN_SEQUENCE, COMPREHENSION) don't contribute — they're inline,
don't change indentation, aren't what §1.4 targets.
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
from savviety_instinct.parse.types import ControlFlowNode, ControlFlowNodeKind

_BLOCK_KINDS: frozenset[ControlFlowNodeKind] = frozenset(
    {
        ControlFlowNodeKind.IF,
        ControlFlowNodeKind.ELIF,
        ControlFlowNodeKind.ELSE,
        ControlFlowNodeKind.FOR,
        ControlFlowNodeKind.WHILE,
        ControlFlowNodeKind.TRY,
        ControlFlowNodeKind.EXCEPT,
    }
)


def _max_depth(nodes: tuple[ControlFlowNode, ...], current: int = 0) -> int:
    best = current
    for node in nodes:
        if node.kind not in _BLOCK_KINDS:
            # Expression-level CFN — don't add depth; still recurse defensively.
            best = max(best, _max_depth(node.children, current))
            continue
        child_depth = _max_depth(node.children, current + 1)
        best = max(best, current + 1, child_depth)
    return best


class MaxNestingDepthMetric:
    id: str = "max_nesting_depth"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})
    shape_invariant: bool = True

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        fn = resolve_function_node(self.id, artifact, context)
        return MetricValue(
            metric_id=self.id,
            value=_max_depth(fn.control_flow),
            metric_version=self.version,
            confidence=Confidence.HIGH,
        )


MAX_NESTING_DEPTH_METRIC = MaxNestingDepthMetric()
