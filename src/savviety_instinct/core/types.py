"""Domain types for Instinct.

Arch spec §5.1. Pure data; no I/O, no DB, no network.
Must not import from any other internal module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class Language(str, Enum):
    PYTHON = "python"
    RUST = "rust"
    CSHARP = "csharp"
    TYPESCRIPT = "typescript"


class ArtifactKind(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InputKind(str, Enum):
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

    Slice 1: placeholder with no fields. Slice 2+ will add call graph,
    module graph, import set, framework indicators, etc. per arch §5.3,
    using keyword-only fields with defaults so construction stays compatible.
    """


@runtime_checkable
class Metric(Protocol):
    id: str
    version: str
    applies_to: frozenset[ArtifactKind]
    required_inputs: frozenset[InputKind]

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue: ...
