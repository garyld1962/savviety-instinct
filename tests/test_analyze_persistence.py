"""Tests for analyze.persistence.run_pipeline_with_persistence.

Exercises the dormant-shortcut behaviour against a recording fake
ObservationStore so we can assert which methods were called without
touching SQLite. Real SQLite end-to-end is exercised in
tests/integration/test_re_run.py (Slice 5 task 6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from savviety_instinct.analyze.persistence import run_pipeline_with_persistence
from savviety_instinct.config.models import InstinctConfig, Scope
from savviety_instinct.core.types import Artifact, ArtifactKind, MetricValue
from savviety_instinct.storage.interfaces import (
    ArtifactId,
    FileLocation,
    Profile,
    Ranking,
    RepoFingerprintSource,
    RunId,
    RunMeta,
    RunStatus,
)


class FakeStore:
    """Recording ObservationStore that mirrors the real semantics in
    memory: dedup by (ast_hash, language, run_metric_version)."""

    def __init__(self) -> None:
        self.runs: dict[int, dict[str, object]] = {}
        # key: (ast_hash, language, metric_version) → (artifact_id, list[MetricValue])
        self.artifacts: dict[tuple[str, str, str], tuple[ArtifactId, list[MetricValue]]] = {}
        # Counter for occurrences keyed by artifact_id
        self.occurrence_counts: dict[ArtifactId, int] = {}
        self.observations: list[tuple[RunId, ArtifactId, FileLocation]] = []
        self.next_run_id = 1
        self.next_artifact_id = 1
        # Call counters for assertions
        self.upsert_calls = 0
        self.shortcut_calls = 0
        self.shortcut_hits = 0
        self.observation_calls = 0
        self.completed_status: RunStatus | None = None

    def begin_run(self, meta: RunMeta) -> RunId:
        run_id = self.next_run_id
        self.next_run_id += 1
        self.runs[run_id] = {"meta": meta, "metric_version": meta.metric_version}
        return run_id

    def complete_run(self, run_id: RunId, status: RunStatus) -> None:
        self.completed_status = status

    def upsert_artifact(
        self, run_id: RunId, artifact: Artifact, metrics: list[MetricValue]
    ) -> ArtifactId:
        self.upsert_calls += 1
        mv = self.runs[run_id]["metric_version"]
        key = (artifact.ast_hash, artifact.language.value, mv)  # type: ignore[arg-type]
        if key in self.artifacts:
            artifact_id, _ = self.artifacts[key]
            self.occurrence_counts[artifact_id] += 1
            return artifact_id
        artifact_id = self.next_artifact_id
        self.next_artifact_id += 1
        self.artifacts[key] = (artifact_id, list(metrics))
        self.occurrence_counts[artifact_id] = 1
        return artifact_id

    def try_dormant_shortcut(
        self, run_id: RunId, ast_hash: str, language: str
    ) -> tuple[ArtifactId, list[MetricValue]] | None:
        self.shortcut_calls += 1
        mv = self.runs[run_id]["metric_version"]
        key = (ast_hash, language, mv)  # type: ignore[arg-type]
        hit = self.artifacts.get(key)
        if hit is None:
            return None
        artifact_id, metrics = hit
        self.occurrence_counts[artifact_id] += 1
        self.shortcut_hits += 1
        return artifact_id, list(metrics)

    def record_observation(
        self, run_id: RunId, artifact_id: ArtifactId, location: FileLocation
    ) -> None:
        self.observation_calls += 1
        self.observations.append((run_id, artifact_id, location))

    def write_ranking(self, run_id: RunId, ranking: Ranking) -> None:
        raise NotImplementedError

    def write_profile(self, run_id: RunId, profile: Profile) -> None:
        raise NotImplementedError


def _meta() -> RunMeta:
    return RunMeta(
        repo_fingerprint="fp_test",
        repo_fingerprint_source=RepoFingerprintSource.SYNTHETIC,
        started_at=datetime.now(UTC),
        commit_sha=None,
        branch=None,
        config_hash="cfg_hash",
        tool_version="0.1.0",
        metric_version="mv_test123456",
    )


def _config() -> InstinctConfig:
    return InstinctConfig(scope=Scope.PERSONAL, suppress=[])


# Tiny fixture file used across tests
_FIXTURE_SOURCE = """
def add(a, b):
    return a + b


def divide(a, b):
    if b == 0:
        return None
    return a / b
"""


@pytest.fixture()
def fixture_path(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(_FIXTURE_SOURCE)
    return p


# ---------- first run (cold path) ----------


def test_first_run_calls_upsert_for_every_artifact(fixture_path: Path) -> None:
    """No prior data: every artifact (1 module + N functions) takes the
    cold path → upsert_artifact called per artifact."""
    store = FakeStore()
    iterator, _summary = run_pipeline_with_persistence(
        fixture_path,
        _config(),
        store,
        cwd=fixture_path.parent,
        run_meta_factory=_meta,
    )
    list(iterator)

    # 1 module + 2 functions = 3 artifacts
    assert store.upsert_calls == 3
    assert store.shortcut_hits == 0


def test_first_run_records_observation_per_artifact(fixture_path: Path) -> None:
    store = FakeStore()
    iterator, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    list(iterator)
    # 1 observation per artifact (3 total)
    assert store.observation_calls == 3


def test_first_run_completes_with_completed_status(fixture_path: Path) -> None:
    store = FakeStore()
    iterator, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    list(iterator)
    assert store.completed_status is RunStatus.COMPLETED


def test_first_run_yields_metric_values(fixture_path: Path) -> None:
    """Wrapper preserves the (Artifact, MetricValue) shape from
    run_pipeline so the existing CLI stdout output is unchanged."""
    store = FakeStore()
    iterator, summary = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    rows = list(iterator)

    assert summary.functions_analyzed == 2
    assert summary.files_parsed == 1
    # At least one MetricValue per function and per module
    function_rows = [(a, m) for a, m in rows if a.kind is ArtifactKind.FUNCTION]
    module_rows = [(a, m) for a, m in rows if a.kind is ArtifactKind.MODULE]
    assert len(function_rows) > 0
    assert len(module_rows) > 0


# ---------- second run (shortcut path) ----------


def test_second_run_takes_shortcut_for_unchanged_artifacts(fixture_path: Path) -> None:
    """After a first run populates the store, a second run on the same
    source must short-circuit every artifact: try_dormant_shortcut hits
    for each, upsert_artifact is NOT called."""
    store = FakeStore()
    # First run
    iterator1, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    list(iterator1)
    upserts_after_first = store.upsert_calls

    # Second run
    iterator2, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    list(iterator2)

    # No new upserts
    assert store.upsert_calls == upserts_after_first
    # Every artifact short-circuited (3 hits in second run)
    assert store.shortcut_hits == 3


def test_second_run_yields_cached_metrics(fixture_path: Path) -> None:
    """Cold-path computed values and shortcut-path cached values must
    match for the same source — no semantic drift on dormant artifacts."""
    store = FakeStore()
    iterator1, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    rows1 = list(iterator1)

    iterator2, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    rows2 = list(iterator2)

    def _values(rows: list[tuple[Artifact, MetricValue]]) -> set[tuple[str, str, object]]:
        return {(a.ast_hash, m.metric_id, m.value) for a, m in rows}

    assert _values(rows1) == _values(rows2)


def test_second_run_records_observations_for_shortcuts(fixture_path: Path) -> None:
    """Even on shortcut, a fresh run_observations row goes in — that's
    how trend tracking sees the artifact in this run."""
    store = FakeStore()
    iterator1, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    list(iterator1)
    obs_after_first = store.observation_calls

    iterator2, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    list(iterator2)
    # Doubled — one fresh batch per run
    assert store.observation_calls == obs_after_first * 2


# ---------- failure path ----------


def test_run_marked_failed_on_exception(tmp_path: Path) -> None:
    """If an exception escapes the pipeline, complete_run is still
    called with FAILED status."""

    class ExplodingStore(FakeStore):
        def upsert_artifact(
            self, run_id: RunId, artifact: Artifact, metrics: list[MetricValue]
        ) -> ArtifactId:
            raise RuntimeError("simulated upsert failure")

    store = ExplodingStore()
    p = tmp_path / "boom.py"
    p.write_text("def f(): pass\n")
    iterator, _ = run_pipeline_with_persistence(
        p, _config(), store, cwd=p.parent, run_meta_factory=_meta
    )
    with pytest.raises(RuntimeError, match="simulated"):
        list(iterator)
    assert store.completed_status is RunStatus.FAILED


def test_path_not_found_raises_eagerly(tmp_path: Path) -> None:
    """Mirrors run_pipeline's eager FileNotFoundError contract."""
    store = FakeStore()
    with pytest.raises(FileNotFoundError):
        run_pipeline_with_persistence(
            tmp_path / "nope.py",
            _config(),
            store,
            cwd=tmp_path,
            run_meta_factory=_meta,
        )


def test_metrics_only_yielded_for_applicable_kinds(fixture_path: Path) -> None:
    """Function-only metrics must NOT yield for module artifacts and
    vice versa — applies_to filter still respected on the shortcut path."""
    from savviety_instinct.analyze import (
        CYCLOMATIC_METRIC,
        TRIVIAL_DELEGATION_RATIO_METRIC,
    )

    store = FakeStore()
    iterator, _ = run_pipeline_with_persistence(
        fixture_path, _config(), store, cwd=fixture_path.parent, run_meta_factory=_meta
    )
    rows = list(iterator)

    # CYCLOMATIC applies_to FUNCTION — never appears on module artifacts
    for artifact, metric in rows:
        if metric.metric_id == CYCLOMATIC_METRIC.id:
            assert artifact.kind is ArtifactKind.FUNCTION
        if metric.metric_id == TRIVIAL_DELEGATION_RATIO_METRIC.id:
            assert artifact.kind is ArtifactKind.MODULE
