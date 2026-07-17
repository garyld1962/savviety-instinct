"""Domain types for Instinct.

Arch spec §5.1. Pure data; no I/O, no DB, no network.
Must not import from any other internal module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from savviety_instinct.graph.types import CallGraph
    from savviety_instinct.parse.types import ParseResult


class Language(StrEnum):
    PYTHON = "python"
    RUST = "rust"
    CSHARP = "csharp"
    TYPESCRIPT = "typescript"


class ArtifactKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InputKind(StrEnum):
    AST = "ast"
    CALL_GRAPH = "call_graph"
    MODULE_GRAPH = "module_graph"
    GIT_HISTORY = "git_history"
    IMPORTS = "imports"
    TYPES = "types"


@dataclass(frozen=True, slots=True)
class SourceRange:
    file_path: str
    line_start: int
    line_end: int


@dataclass(frozen=True, slots=True)
class Artifact:
    ast_hash: str
    language: Language
    kind: ArtifactKind
    name: str
    enclosing_scope: str | None
    source_range: SourceRange


@dataclass(frozen=True, slots=True)
class MetricValue:
    metric_id: str
    # Numeric for counts and ratios; str for categorical metrics like
    # stability_tier ("volatile" | "settled" | "dormant"). Do not narrow.
    value: float | int | str
    metric_version: str
    confidence: Confidence
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Context passed to each Metric.compute().

    Slice 2 added `call_graph`. Slice 3 adds `parse_result` so metrics can
    look up their own function's ControlFlowNode / statement_count without
    a second tree walk. All fields are keyword-only with defaults; the
    absolute core → (parse|graph) layering rule is preserved via
    TYPE_CHECKING + string annotations (arch §2).
    """

    call_graph: "CallGraph | None" = None  # noqa: UP037 — quoted for explicit forward-ref
    parse_result: "ParseResult | None" = None  # noqa: UP037 — quoted for explicit forward-ref


@runtime_checkable
class Metric(Protocol):
    id: str
    version: str
    applies_to: frozenset[ArtifactKind]
    required_inputs: frozenset[InputKind]
    # True when the value is fully determined by the identifier/literal-blind
    # AST shape that ast_hash captures (arch §4.2). False for metrics that
    # read identifier text (e.g. identifier_quality, delegation classification):
    # their values are per-occurrence and MUST NOT be served from any cache or
    # store row keyed on ast_hash — shape-identical code can score differently.
    shape_invariant: bool

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue: ...
