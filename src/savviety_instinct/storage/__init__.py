"""Storage layer — repository pattern Protocols and SQLAlchemy impl."""

from savviety_instinct.storage.fingerprint import derive_repo_fingerprint
from savviety_instinct.storage.interfaces import (
    ArtifactId,
    FileLocation,
    Observation,
    ObservationQuery,
    ObservationStore,
    Profile,
    ProfileAxis,
    ProfileStatus,
    RankedObservation,
    Ranking,
    RepoFingerprintSource,
    Run,
    RunId,
    RunMeta,
    RunStatus,
    Trend,
    TrendPoint,
)
from savviety_instinct.storage.run_meta import (
    compute_combined_metric_version,
    compute_config_hash,
    derive_git_commit_branch,
)
from savviety_instinct.storage.sqlite_store import SQLAlchemyObservationStore

__all__ = [
    "ArtifactId",
    "FileLocation",
    "Observation",
    "ObservationQuery",
    "ObservationStore",
    "Profile",
    "ProfileAxis",
    "ProfileStatus",
    "Ranking",
    "RankedObservation",
    "RepoFingerprintSource",
    "Run",
    "RunId",
    "RunMeta",
    "RunStatus",
    "SQLAlchemyObservationStore",
    "Trend",
    "TrendPoint",
    "compute_combined_metric_version",
    "compute_config_hash",
    "derive_git_commit_branch",
    "derive_repo_fingerprint",
]
