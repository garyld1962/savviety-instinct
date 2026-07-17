"""Tests for savviety_instinct.storage.interfaces (arch §5.2)."""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    MetricValue,
    SourceRange,
)
from savviety_instinct.storage.interfaces import (
    FileLocation,
    Observation,
    ObservationQuery,
    ObservationStore,
    Profile,
    RankedObservation,
    Ranking,
    RepoFingerprintSource,
    Run,
    RunMeta,
    RunStatus,
    Trend,
)


def _sample_artifact() -> Artifact:
    return Artifact(
        ast_hash="h1",
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name="foo",
        enclosing_scope=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=5),
    )


def test_run_status_values():
    assert {s.value for s in RunStatus} == {"running", "completed", "failed"}


def test_repo_fingerprint_source_values():
    assert {s.value for s in RepoFingerprintSource} == {
        "first_commit",
        "origin_url",
        "synthetic",
    }


def test_run_meta_is_frozen_dataclass():
    m = RunMeta(
        repo_fingerprint="fp",
        repo_fingerprint_source=RepoFingerprintSource.FIRST_COMMIT,
        started_at=datetime(2026, 4, 16, 12, 0, 0),
        commit_sha="abc123",
        branch="main",
        config_hash="ch",
        tool_version="0.1.0",
        metric_version="0.0.0-slice1",
    )
    assert m.commit_sha == "abc123"
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.commit_sha = "deadbeef"  # type: ignore[misc]


def test_file_location_fields():
    loc = FileLocation(
        file_path="x.py",
        line_start=1,
        line_end=5,
        symbol_name="foo",
        enclosing_scope=None,
        context_hash="ctx",
    )
    assert loc.context_hash == "ctx"


class _FakeStore:
    """Minimal stub that satisfies the ObservationStore Protocol shape."""

    def __init__(self) -> None:
        self.runs: dict[int, RunMeta] = {}

    def begin_run(self, meta: RunMeta) -> int:
        run_id = len(self.runs) + 1
        self.runs[run_id] = meta
        return run_id

    def complete_run(self, run_id: int, status: RunStatus) -> None:
        _ = (run_id, status)

    def upsert_artifact(self, run_id: int, artifact: Artifact, metrics: list[MetricValue]) -> int:
        _ = (run_id, artifact, metrics)
        return 1

    def try_dormant_shortcut(
        self, run_id: int, ast_hash: str, language: str
    ) -> tuple[int, list[MetricValue]] | None:
        _ = (run_id, ast_hash, language)
        return None

    def record_observation(self, run_id: int, artifact_id: int, location: FileLocation) -> None:
        _ = (run_id, artifact_id, location)

    def write_ranking(self, run_id: int, ranking: Ranking) -> None:
        _ = (run_id, ranking)

    def write_profile(self, run_id: int, profile: Profile) -> None:
        _ = (run_id, profile)


class _FakeQuery:
    def get_run(self, run_id: int) -> Run:
        raise NotImplementedError

    def get_rankings(self, run_id: int, limit: int) -> list[RankedObservation]:
        return []

    def get_profile(self, run_id: int) -> Profile:
        raise NotImplementedError

    def get_trend(self, window_days: int) -> Trend:
        raise NotImplementedError

    def get_artifact_history(self, ast_hash: str) -> list[Observation]:
        return []


def test_fake_store_satisfies_protocol():
    assert isinstance(_FakeStore(), ObservationStore)


def test_fake_query_satisfies_protocol():
    assert isinstance(_FakeQuery(), ObservationQuery)


def test_begin_run_roundtrip():
    store = _FakeStore()
    run_id = store.begin_run(
        RunMeta(
            repo_fingerprint="fp",
            repo_fingerprint_source=RepoFingerprintSource.SYNTHETIC,
            started_at=datetime.now(),
            commit_sha=None,
            branch=None,
            config_hash="ch",
            tool_version="0.1.0",
            metric_version="0.0.0-slice1",
        )
    )
    assert run_id == 1
    assert store.runs[1].repo_fingerprint == "fp"


def test_upsert_artifact_returns_id():
    store = _FakeStore()
    aid = store.upsert_artifact(
        1,  # run_id
        _sample_artifact(),
        [
            MetricValue(
                metric_id="m",
                value=0,
                metric_version="0.0.0-slice1",
                confidence=Confidence.HIGH,
            )
        ],
    )
    assert aid == 1
    # silence unused-import lint for AnalysisContext
    _ = AnalysisContext()


def test_observation_store_rejects_missing_method():
    class MissingWriteRanking:
        def begin_run(self, meta: RunMeta) -> int:
            return 0

        def complete_run(self, run_id: int, status: RunStatus) -> None:
            _ = (run_id, status)

        def upsert_artifact(
            self, run_id: int, artifact: Artifact, metrics: list[MetricValue]
        ) -> int:
            _ = (run_id, artifact, metrics)
            return 0

        def try_dormant_shortcut(
            self, run_id: int, ast_hash: str, language: str
        ) -> tuple[int, list[MetricValue]] | None:
            _ = (run_id, ast_hash, language)
            return None

        def record_observation(self, run_id: int, artifact_id: int, location: FileLocation) -> None:
            _ = (run_id, artifact_id, location)

        # intentionally missing: write_ranking, write_profile

    assert not isinstance(MissingWriteRanking(), ObservationStore)


def test_observation_query_rejects_missing_method():
    class MissingGetProfile:
        def get_run(self, run_id: int) -> Run:
            raise NotImplementedError

        def get_rankings(self, run_id: int, limit: int) -> list[RankedObservation]:
            return []

        # intentionally missing: get_profile, get_trend, get_artifact_history

    assert not isinstance(MissingGetProfile(), ObservationQuery)
