"""SQLAlchemy-backed `ObservationStore` for per-repo SQLite per D10.

Slice 5 task 2: run-lifecycle (`begin_run`, `complete_run`).
Slice 5 task 3: `upsert_artifact` with dedup + stability-tier
transitions, and `record_observation`. Ranking + profile writes are
deferred to Slice 6 and raise `NotImplementedError`.

Auto-upgrades the schema to head on construction (Slice 5 Scope #10):
zero-friction for the MVP user; the Alembic Config object is cached
module-level so per-test cost amortizes.
"""

from __future__ import annotations

import json
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

_STABILITY_VOLATILE = "volatile"
_STABILITY_SETTLED = "settled"


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

    # ---------- artifact upsert + observation recording ----------

    def upsert_artifact(
        self, run_id: RunId, artifact: Artifact, metrics: list[MetricValue]
    ) -> ArtifactId:
        """Insert a new artifact row, or update an existing one if its
        `(ast_hash, language, metric_version)` already exists for the
        current run's combined `metric_version`.

        On insert:
            occurrence_count = 1, stability_tier = 'volatile'.
        On update:
            occurrence_count += 1; stability_tier transitions to
            'settled' once count >= 2 (Slice 5 Scope #3 — minimal tier
            policy until Slice 6 surfaces a real consumer).

        Returns the artifact_id either way.
        """
        metrics_json = json.dumps(
            {
                m.metric_id: {
                    "value": m.value,
                    "version": m.metric_version,
                    "confidence": m.confidence.value,
                    **({"notes": m.notes} if m.notes is not None else {}),
                }
                for m in metrics
            },
            sort_keys=True,
        )

        with self._engine.begin() as conn:
            run_row = conn.execute(
                text("SELECT repo_fingerprint, metric_version FROM runs WHERE id = :id"),
                {"id": run_id},
            ).fetchone()
            if run_row is None:
                raise LookupError(f"upsert_artifact: run_id {run_id} not found")
            repo_fingerprint, combined_metric_version = run_row

            existing = conn.execute(
                text(
                    """
                    SELECT id, occurrence_count
                      FROM observation_artifacts
                     WHERE ast_hash = :ast_hash
                       AND language = :language
                       AND metric_version = :metric_version
                    """
                ),
                {
                    "ast_hash": artifact.ast_hash,
                    "language": artifact.language.value,
                    "metric_version": combined_metric_version,
                },
            ).fetchone()

            if existing is not None:
                artifact_id, prior_count = existing
                new_count = int(prior_count) + 1
                new_tier = _STABILITY_SETTLED if new_count >= 2 else _STABILITY_VOLATILE
                conn.execute(
                    text(
                        """
                        UPDATE observation_artifacts
                           SET last_seen_run_id = :run_id,
                               occurrence_count = :count,
                               stability_tier = :tier
                         WHERE id = :id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "count": new_count,
                        "tier": new_tier,
                        "id": artifact_id,
                    },
                )
                return int(artifact_id)

            inserted = conn.execute(
                text(
                    """
                    INSERT INTO observation_artifacts (
                        repo_fingerprint, ast_hash, language, artifact_kind,
                        metrics_json, metric_version,
                        first_seen_run_id, last_seen_run_id,
                        occurrence_count, stability_tier
                    ) VALUES (
                        :fp, :ast_hash, :language, :kind,
                        :metrics_json, :metric_version,
                        :run_id, :run_id,
                        1, :tier
                    )
                    RETURNING id
                    """
                ),
                {
                    "fp": repo_fingerprint,
                    "ast_hash": artifact.ast_hash,
                    "language": artifact.language.value,
                    "kind": artifact.kind.value,
                    "metrics_json": metrics_json,
                    "metric_version": combined_metric_version,
                    "run_id": run_id,
                    "tier": _STABILITY_VOLATILE,
                },
            )
            return int(inserted.scalar_one())

    def record_observation(
        self, run_id: RunId, artifact_id: ArtifactId, location: FileLocation
    ) -> None:
        """Insert a `run_observations` link row. One per artifact
        sighting per run; the TTL (D7, deferred from Slice 5) eventually
        trims these while keeping the underlying artifact rows."""
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO run_observations (
                        run_id, artifact_id, file_path, line_start, line_end,
                        symbol_name, enclosing_scope, context_hash
                    ) VALUES (
                        :run_id, :artifact_id, :file_path, :line_start, :line_end,
                        :symbol_name, :enclosing_scope, :context_hash
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "artifact_id": artifact_id,
                    "file_path": location.file_path,
                    "line_start": location.line_start,
                    "line_end": location.line_end,
                    "symbol_name": location.symbol_name,
                    "enclosing_scope": location.enclosing_scope,
                    "context_hash": location.context_hash,
                },
            )

    # ---------- not yet implemented (Slice 6) ----------

    def write_ranking(self, run_id: RunId, ranking: Ranking) -> None:
        raise NotImplementedError("write_ranking lands in Slice 6")

    def write_profile(self, run_id: RunId, profile: Profile) -> None:
        raise NotImplementedError("write_profile lands in Slice 6")
