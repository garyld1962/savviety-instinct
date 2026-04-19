"""Cognitive Complexity (Campbell / Sonar) metric.

Arch §1.2. Walks the ControlFlowNode tree tracking cumulative nesting depth
and applies per-language increment rules loaded from YAML. The nesting
counter is advanced based on the rule's `increments_nesting` flag, NOT the
raw parse-level `ControlFlowNode.nesting_depth` — this keeps the parser
rule-agnostic.
"""

from __future__ import annotations

from savviety_instinct.analyze.rules import CognitiveRules, load_cognitive_rules
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)
from savviety_instinct.parse.types import ControlFlowNode


def _compute(nodes: tuple[ControlFlowNode, ...], rules: CognitiveRules, nesting: int = 0) -> int:
    total = 0
    for node in nodes:
        rule = rules.increments[node.kind]
        if rule.base > 0:
            total += rule.base + nesting
        child_nesting = nesting + (1 if rule.increments_nesting else 0)
        total += _compute(node.children, rules, child_nesting)
    return total


class CognitiveMetric:
    id: str = "cognitive_complexity"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result to be populated.")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                rules = load_cognitive_rules(context.parse_result.language)
                value = _compute(fn.control_flow, rules)
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


COGNITIVE_METRIC = CognitiveMetric()
