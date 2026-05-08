"""SQLAlchemy-backed `ObservationStore` for per-repo SQLite per D10.

Slice 5 task 2: skeleton with run-lifecycle methods (`begin_run`,
`complete_run`). Artifact upsert / observation recording arrive in
task 3; ranking + profile writes are deferred to Slice 6 and raise
`NotImplementedError` in the meantime to keep the Protocol shape.

Auto-upgrades the schema to head on construction (Slice 5 Scope #10):
zero-friction for the MVP user; the Alembic Config object is cached
module-level so per-test cost amortizes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache
from importlib import resources
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text

from savviety_instinct.core.types import Artifact, MetricValue
from savviety_instinct.storage.interfaces import (
    ArtifactId,
    FileLocation,
    Profile,
    Ranking,
    RunId,
    RunMeta,
    RunStatus,
)


@cache
def _migrations_script_location() -> str:
    """Absolute path to the migrations package, resolved via importlib
    resources so the store works regardless of cwd.
    Cached because resolving the path involves filesystem lookups."""
    return str(resources.files("savviety_instinct.storage.migrations"))


def _alembic_config(url: str) -> Config:
    """Programmatic Alembic config — no `alembic.ini` lookup. Caller
    supplies the SQLAlchemy URL; everything else is fixed."""
    cfg = Config()
    cfg.set_main_option("script_location", _migrations_script_location())
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _create_engine(db_path: Path) -> Engine:
    """Create an Engine for the given SQLite path with the arch §8.3
    pragmas (`journal_mode=WAL`, `synchronous=NORMAL`) applied to every
    connection. Listener is per-engine, not global, so other tests'
    engines aren't affected."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.close()

    return engine


class SQLAlchemyObservationStore:
    """Concrete `ObservationStore` Protocol impl backed by per-repo
    SQLite. Constructed once per `instinct run` invocation.

    Per Slice 5 Scope #10, schema is auto-upgraded to head on init.
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
        command.upgrade(_alembic_config(url), "head")
        self._engine = _create_engine(db_path)

    # ---------- run lifecycle ----------

    def begin_run(self, meta: RunMeta) -> RunId:
        """Insert a new `runs` row in 'running' status; return its id."""
        with self._engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO runs (
                        repo_fingerprint, repo_fingerprint_source, started_at,
                        commit_sha, branch, config_hash, tool_version,
                        metric_version, status, notes
                    ) VALUES (
                        :fp, :fp_src, :started_at,
                        :commit_sha, :branch, :config_hash, :tool_version,
                        :metric_version, :status, :notes
                    )
                    RETURNING id
                    """
                ),
                {
                    "fp": meta.repo_fingerprint,
                    "fp_src": meta.repo_fingerprint_source.value,
                    "started_at": meta.started_at,
                    "commit_sha": meta.commit_sha,
                    "branch": meta.branch,
                    "config_hash": meta.config_hash,
                    "tool_version": meta.tool_version,
                    "metric_version": meta.metric_version,
                    "status": RunStatus.RUNNING.value,
                    "notes": meta.notes,
                },
            )
            row = result.fetchone()
            assert row is not None, "INSERT ... RETURNING produced no row"
            return int(row[0])

    def complete_run(self, run_id: RunId, status: RunStatus) -> None:
        """Mark the run finished with the given terminal status and
        stamp `completed_at` to the current UTC time."""
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE runs
                       SET status = :status,
                           completed_at = :completed_at
                     WHERE id = :id
                    """
                ),
                {
                    "status": status.value,
                    "completed_at": datetime.now(UTC),
                    "id": run_id,
                },
            )

    # ---------- not yet implemented (filled in by later Slice 5 / 6 tasks) ----------

    def upsert_artifact(self, artifact: Artifact, metrics: list[MetricValue]) -> ArtifactId:
        raise NotImplementedError("upsert_artifact lands in Slice 5 task 3")

    def record_observation(
        self, run_id: RunId, artifact_id: ArtifactId, location: FileLocation
    ) -> None:
        raise NotImplementedError("record_observation lands in Slice 5 task 3")

    def write_ranking(self, run_id: RunId, ranking: Ranking) -> None:
        raise NotImplementedError("write_ranking lands in Slice 6")

    def write_profile(self, run_id: RunId, profile: Profile) -> None:
        raise NotImplementedError("write_profile lands in Slice 6")
