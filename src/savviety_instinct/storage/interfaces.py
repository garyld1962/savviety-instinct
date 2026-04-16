"""Storage layer Protocols — the only module that knows about SQL.

Arch spec §5.2. Concrete SQLAlchemy implementation lands in Slice 2+.
Slice 1 defines the Protocols + data types so higher layers can depend on
interfaces, not implementations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from savviety_instinct.core.types import Artifact, MetricValue

RunId = int
ArtifactId = int


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RepoFingerprintSource(StrEnum):
    """Three derivation tiers per D10. Populated on `runs.repo_fingerprint_source`."""

    FIRST_COMMIT = "first_commit"
    ORIGIN_URL = "origin_url"
    SYNTHETIC = "synthetic"


class ProfileStatus(StrEnum):
    NORMAL = "normal"
    WATCH = "watch"
    ELEVATED = "elevated"


@dataclass(frozen=True, slots=True)
class RunMeta:
    repo_fingerprint: str
    repo_fingerprint_source: RepoFingerprintSource
    started_at: datetime
    commit_sha: str | None
    branch: str | None
    config_hash: str
    tool_version: str
    metric_version: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class FileLocation:
    file_path: str
    line_start: int
    line_end: int
    symbol_name: str
    enclosing_scope: str | None
    context_hash: str  # D6 forward-compat: dedicated column on run_observations


@dataclass(frozen=True, slots=True)
class Ranking:
    run_observation_id: int
    attention_priority: float
    rank: int
    contributing_metrics_json: str


@dataclass(frozen=True, slots=True)
class ProfileAxis:
    name: str
    p50: float | None
    p90: float | None
    p95: float | None
    p99: float | None
    status: ProfileStatus
    sample_size: int


@dataclass(frozen=True, slots=True)
class Profile:
    axes: Mapping[str, ProfileAxis]


@dataclass(frozen=True, slots=True)
class Run:
    id: int
    meta: RunMeta
    completed_at: datetime | None
    status: RunStatus


@dataclass(frozen=True, slots=True)
class Observation:
    run_id: int
    artifact_id: int
    file_location: FileLocation


@dataclass(frozen=True, slots=True)
class RankedObservation:
    run_observation_id: int
    artifact_id: int
    file_location: FileLocation
    ranking: Ranking


@dataclass(frozen=True, slots=True)
class TrendPoint:
    run_id: int
    at: datetime
    axis: str
    value: float


@dataclass(frozen=True, slots=True)
class Trend:
    window_days: int
    points: tuple[TrendPoint, ...]


@runtime_checkable
class ObservationStore(Protocol):
    """Write-side repository. `@runtime_checkable` enables isinstance guards at
    framework entry points; note it checks method presence only, not signatures —
    rely on mypy for signature validation.
    """

    def begin_run(self, meta: RunMeta) -> RunId: ...
    def complete_run(self, run_id: RunId, status: RunStatus) -> None: ...
    def upsert_artifact(self, artifact: Artifact, metrics: list[MetricValue]) -> ArtifactId: ...
    def record_observation(
        self, run_id: RunId, artifact_id: ArtifactId, location: FileLocation
    ) -> None: ...
    def write_ranking(self, run_id: RunId, ranking: Ranking) -> None: ...
    def write_profile(self, run_id: RunId, profile: Profile) -> None: ...


@runtime_checkable
class ObservationQuery(Protocol):
    """Read-side repository. See ObservationStore for the runtime_checkable caveat."""

    def get_run(self, run_id: RunId) -> Run: ...
    def get_rankings(self, run_id: RunId, limit: int) -> list[RankedObservation]: ...
    def get_profile(self, run_id: RunId) -> Profile: ...
    def get_trend(self, window_days: int) -> Trend: ...
    def get_artifact_history(self, ast_hash: str) -> list[Observation]: ...
