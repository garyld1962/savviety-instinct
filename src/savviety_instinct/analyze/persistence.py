"""Pipeline wrapper that persists observations through `ObservationStore`.

The bare `analyze.pipeline.run_pipeline` is a pure generator with no
storage knowledge — preserved so unit tests of metrics keep bypassing
the DB. This wrapper composes `run_pipeline`'s machinery with the store
and adds the dormant-artifact shortcut (arch §8.2): on artifacts whose
`(ast_hash, language, combined_metric_version)` already exist, skip
shape-invariant metric computation and yield the cached values straight
from the row.

ast_hash is identifier/literal-blind, so the artifact row represents a
SHAPE, not a code location. Metrics with `shape_invariant=False`
(identifier_quality, trivial_delegation_ratio) are excluded from the
row's metrics_json and recomputed per occurrence on both paths —
serving them from a shape-keyed cache returns another occurrence's (or
an earlier rename's) values.

Per Slice 5 Scope #5, `context_hash` is partial: derived from
`(language, enclosing_class_or_empty, caller_count, callee_count)`.
The full D6 composition arrives in R2.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from savviety_instinct import __version__
from savviety_instinct.analyze.pipeline import PipelineSummary, _discover_files
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
from savviety_instinct.parse.types import FunctionDefNode, ParseResult
from savviety_instinct.storage.fingerprint import derive_repo_fingerprint
from savviety_instinct.storage.interfaces import (
    FileLocation,
    ObservationStore,
    RunMeta,
    RunStatus,
)
from savviety_instinct.storage.run_meta import (
    compute_combined_metric_version,
    compute_config_hash,
    derive_git_commit_branch,
)


def _module_ast_hash(functions: tuple[FunctionDefNode, ...]) -> str:
    joined = "|".join(fn.ast_hash for fn in functions)
    return hash_ast_sexp(joined)


def _caller_callee_counts(artifact: Artifact, parse_result: ParseResult) -> tuple[int, int]:
    """(caller_count, callee_count) for `context_hash`.

    Function artifacts: callees are CallSites whose `enclosing_function`
    is this function's qualified name; callers are *resolved* CallSites
    whose `callee_name` matches this function's bare `name` (intra-file
    resolution from Slice 2).
    Module artifacts: callee_count is the file's total CallSites;
    caller_count is 0 (modules aren't called within the file).
    Class artifacts: not emitted by the pipeline today; both 0.
    """
    if artifact.kind is ArtifactKind.MODULE:
        return 0, len(parse_result.call_sites)
    if artifact.kind is ArtifactKind.FUNCTION:
        qualified = (
            f"{artifact.enclosing_scope}.{artifact.name}"
            if artifact.enclosing_scope is not None
            else artifact.name
        )
        callee_count = sum(
            1 for cs in parse_result.call_sites if cs.enclosing_function == qualified
        )
        caller_count = sum(
            1
            for cs in parse_result.call_sites
            if cs.is_resolved and cs.callee_name == artifact.name
        )
        return caller_count, callee_count
    return 0, 0


def _context_hash(artifact: Artifact, parse_result: ParseResult) -> str:
    """Partial D6 context hash for Slice 5: language, enclosing class,
    caller count, callee count. Extended in R2 with import set,
    framework indicators, caller/callee signatures."""
    caller_count, callee_count = _caller_callee_counts(artifact, parse_result)
    enclosing = artifact.enclosing_scope or ""
    payload = f"{artifact.language.value}|{enclosing}|{caller_count}|{callee_count}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_location(artifact: Artifact, parse_result: ParseResult) -> FileLocation:
    return FileLocation(
        file_path=artifact.source_range.file_path,
        line_start=artifact.source_range.line_start,
        line_end=artifact.source_range.line_end,
        symbol_name=artifact.name,
        enclosing_scope=artifact.enclosing_scope,
        context_hash=_context_hash(artifact, parse_result),
    )


def _build_run_meta(
    cwd: Path,
    config: InstinctConfig,
    combined_metric_version: str,
) -> RunMeta:
    repo_fingerprint, fp_source = derive_repo_fingerprint(cwd)
    commit_sha, branch = derive_git_commit_branch(cwd)
    return RunMeta(
        repo_fingerprint=repo_fingerprint,
        repo_fingerprint_source=fp_source,
        started_at=datetime.now(UTC),
        commit_sha=commit_sha,
        branch=branch,
        config_hash=compute_config_hash(config),
        tool_version=__version__,
        metric_version=combined_metric_version,
    )


def run_pipeline_with_persistence(
    path: Path,
    config: InstinctConfig,
    store: ObservationStore,
    cwd: Path | None = None,
    run_meta_factory: Callable[[], RunMeta] | None = None,
) -> tuple[Iterator[tuple[Artifact, MetricValue]], PipelineSummary]:
    """Same-shaped contract as `analyze.pipeline.run_pipeline` plus
    persistence side effects. Yields `(Artifact, MetricValue)` tuples
    so the existing CLI stdout output is unchanged.

    `cwd` defaults to `Path.cwd()` and is the directory used for
    repo_fingerprint and commit/branch lookup.
    `run_meta_factory` is an injection point for tests; production callers
    can leave it None and a default RunMeta is built from cwd+config.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    cwd_path = cwd if cwd is not None else Path.cwd()
    summary = PipelineSummary()

    def _iter() -> Iterator[tuple[Artifact, MetricValue]]:
        # Lazy import for the same monkeypatch reason as run_pipeline.
        from savviety_instinct.analyze import METRICS_REGISTRY

        combined_metric_version = compute_combined_metric_version(METRICS_REGISTRY)
        meta = (
            run_meta_factory()
            if run_meta_factory is not None
            else _build_run_meta(cwd_path, config, combined_metric_version)
        )
        run_id = store.begin_run(meta)
        completed = False
        try:
            files = _discover_files(path, config.suppress)
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

                ctx = AnalysisContext(parse_result=result)
                for artifact in [module_artifact, *function_artifacts]:
                    location = _file_location(artifact, result)
                    applicable = [
                        metric for metric in METRICS_REGISTRY if artifact.kind in metric.applies_to
                    ]
                    shortcut = store.try_dormant_shortcut(
                        run_id, artifact.ast_hash, artifact.language.value
                    )
                    if shortcut is not None:
                        # Cached values are shape-invariant only; the rest are
                        # per-occurrence and computed fresh for THIS location.
                        artifact_id, metrics = shortcut
                        metrics = metrics + [
                            metric.compute(artifact, ctx)
                            for metric in applicable
                            if not metric.shape_invariant
                        ]
                    else:
                        computed = [
                            (metric, metric.compute(artifact, ctx)) for metric in applicable
                        ]
                        metrics = [value for _, value in computed]
                        artifact_id = store.upsert_artifact(
                            run_id,
                            artifact,
                            [value for metric, value in computed if metric.shape_invariant],
                        )
                    store.record_observation(run_id, artifact_id, location)
                    for m in metrics:
                        yield artifact, m
            completed = True
        finally:
            status = RunStatus.COMPLETED if completed else RunStatus.FAILED
            store.complete_run(run_id, status)

    return _iter(), summary
