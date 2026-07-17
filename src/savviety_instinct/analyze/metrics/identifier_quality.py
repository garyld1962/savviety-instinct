"""Identifier Quality heuristic metric (arch §4.1).

R1 heuristic; LLM-augmented refinement is R2. Combines the function's
own name, parameter names, and body identifier occurrences into a single
set and counts how many are "meaningful" via a simple length + stopword
heuristic.

Confidence: LOW (per arch §4.1 "heuristic, low confidence").

KNOWN GAPS (metric_version=1.1.0):
- Context-aware exemption (e.g., `x` meaningful in math context) not implemented.
- Idiomatic short names (`n`, `m`) treated as non-meaningful.
- Occurrence frequency ignored; distinct names only.

VERSION HISTORY:
- 1.1.0: FunctionDefNode resolved by source_range instead of ast_hash.
  Values change where shape-identical functions coexist in one file —
  each function now scores from its own identifiers instead of the
  first shape-match's.
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

# Stopword list locked for Slice 4a; changes require a metric_version bump.
STOPWORDS: frozenset[str] = frozenset({"i", "j", "k", "x", "y", "z", "tmp", "foo", "bar", "baz"})


def _is_meaningful(identifier: str) -> bool:
    return len(identifier) >= 3 and identifier not in STOPWORDS


class IdentifierQualityMetric:
    id: str = "identifier_quality"
    version: str = "1.1.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})
    # Reads identifier text, which ast_hash deliberately omits: two
    # shape-identical functions can score differently. Never cache by shape.
    shape_invariant: bool = False

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        fn = resolve_function_node(self.id, artifact, context)
        all_identifiers = {fn.name} | set(fn.parameter_names) | set(fn.identifier_names)
        meaningful = {i for i in all_identifiers if _is_meaningful(i)}
        quality = len(meaningful) / max(len(all_identifiers), 1)
        return MetricValue(
            metric_id=self.id,
            value=quality,
            metric_version=self.version,
            confidence=Confidence.LOW,
        )


IDENTIFIER_QUALITY_METRIC = IdentifierQualityMetric()
