"""Analysis pipeline — walk a path, parse each source file, compute metrics.

Arch §5.3. Slice 3: single-threaded, synchronous, no storage writes. Yields
`(Artifact, MetricValue)` tuples for CLI consumers. Parse errors are soft —
file skipped, logged to stderr, counted in summary. Non-parse errors
propagate.
"""

from __future__ import annotations

import fnmatch
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Language,
    MetricValue,
    SourceRange,
)
from savviety_instinct.parse.hashing import hash_ast_sexp
from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import FunctionDefNode


@dataclass
class PipelineSummary:
    """Mutable summary. Callers drain the iterator before reading."""

    files_parsed: int = 0
    files_skipped: int = 0
    functions_analyzed: int = 0


def run_pipeline(
    path: Path, config: InstinctConfig
) -> tuple[Iterator[tuple[Artifact, MetricValue]], PipelineSummary]:
    """Return (generator of (Artifact, MetricValue), summary).

    The summary is a mutable dataclass updated as the generator yields. Callers
    should drain the iterator before reading summary fields.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    summary = PipelineSummary()
    files = _discover_files(path, config.suppress)

    def _iter() -> Iterator[tuple[Artifact, MetricValue]]:
        from savviety_instinct.analyze import METRICS_REGISTRY  # lazy; avoids cycle

        for source_path in files:
            result = PYTHON_ADAPTER.parse_path(source_path)
            if not result.ok:
                summary.files_skipped += 1
                err = result.errors[0] if result.errors else None
                print(
                    f"[parse-error] {source_path}: {err.message if err else 'unknown'}",
                    file=sys.stderr,
                )
                continue
            summary.files_parsed += 1
            ctx = AnalysisContext(parse_result=result)

            # Slice 4b: build MODULE artifact for this file.
            module_artifact = Artifact(
                ast_hash=_module_ast_hash(result.functions),
                language=Language.PYTHON,
                kind=ArtifactKind.MODULE,
                name=str(source_path),
                enclosing_scope=None,
                source_range=SourceRange(
                    file_path=str(source_path),
                    line_start=1,
                    line_end=max(result.line_count, 1),
                ),
            )

            # Build FUNCTION artifacts.
            function_artifacts: list[Artifact] = []
            for fn in result.functions:
                summary.functions_analyzed += 1
                function_artifacts.append(
                    Artifact(
                        ast_hash=fn.ast_hash,
                        language=Language.PYTHON,
                        kind=ArtifactKind.FUNCTION,
                        name=fn.name,
                        enclosing_scope=fn.enclosing_class,
                        source_range=fn.source_range,
                    )
                )

            # Dispatch: module first for deterministic ordering, then functions.
            # Apply applies_to filter so each metric only fires on its intended kinds.
            for artifact in [module_artifact, *function_artifacts]:
                for metric in METRICS_REGISTRY:
                    if artifact.kind in metric.applies_to:
                        yield artifact, metric.compute(artifact, ctx)

    return _iter(), summary


def _discover_files(path: Path, suppress: list[str]) -> list[Path]:
    """Enumerate .py files under path honoring glob suppressions.

    Returns a sorted list for deterministic iteration. `path` may be a file
    (returned as-is unless suppressed) or a directory.
    """
    if path.is_file():
        if _is_suppressed(path, suppress):
            return []
        return [path] if path.suffix == ".py" else []
    candidates = sorted(path.rglob("*.py"))
    return [p for p in candidates if not _is_suppressed(p, suppress)]


def _is_suppressed(path: Path, patterns: list[str]) -> bool:
    s = str(path)
    return any(fnmatch.fnmatch(s, pat) for pat in patterns)


def _module_ast_hash(functions: tuple[FunctionDefNode, ...]) -> str:
    """Shape-invariant hash for a module artifact.

    Defined as hash_ast_sexp(joined function ast_hashes). Changes when a
    function is added, removed, or structurally modified; invariant across
    identifier/literal renames (per-function ast_hash is already invariant).

    Modules with zero functions get a stable hash of the empty joined string;
    consistent across empty modules. Uses hash_ast_sexp so the backend
    (blake3 / xxhash) is consistent with per-function ast_hash from Slice 2.
    """
    joined = "|".join(fn.ast_hash for fn in functions)
    return hash_ast_sexp(joined)
