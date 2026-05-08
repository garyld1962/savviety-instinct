"""Tests for SQLAlchemyObservationStore — covers Slice 5 tasks 2 and 3:
constructor schema upgrade, run lifecycle, artifact upsert with dedup,
stability-tier transitions, and observation recording."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from savviety_instinct.core.types import (
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    MetricValue,
    SourceRange,
)
from savviety_instinct.storage.interfaces import (
    FileLocation,
    RepoFingerprintSource,
    RunMeta,
    RunStatus,
)
from savviety_instinct.storage.sqlite_store import SQLAlchemyObservationStore


def _meta(**overrides: object) -> RunMeta:
    base = {
        "repo_fingerprint": "fp" + "0" * 62,
        "repo_fingerprint_source": RepoFingerprintSource.SYNTHETIC,
        "started_at": datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC),
        "commit_sha": None,
        "branch": None,
        "config_hash": "c" * 64,
        "tool_version": "0.1.0",
        "metric_version": "mv_abcdef012345",
        "notes": None,
    }
    base.update(overrides)
    return RunMeta(**base)  # type: ignore[arg-type]


def _expected_tables() -> set[str]:
    return {
        "runs",
        "observation_artifacts",
        "run_observations",
        "rankings",
        "run_profiles",
        "llm_verdicts",
        "patterns",
        "pattern_evidence",
    }


# ---------- constructor / schema ----------


def test_constructor_creates_schema_at_head(tmp_path: Path) -> None:
    """Instantiating the store on a fresh path should run alembic upgrade
    head, leaving every expected table in place."""
    db_path = tmp_path / "instinct.db"
    SQLAlchemyObservationStore(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert _expected_tables().issubset(tables)


def test_constructor_creates_parent_dirs(tmp_path: Path) -> None:
    """Path with non-existent parent dir is created (mirrors `instinct
    init` scaffolding `.instinct/`)."""
    db_path = tmp_path / "nested" / "deeper" / "instinct.db"
    assert not db_path.parent.exists()
    SQLAlchemyObservationStore(db_path)
    assert db_path.parent.exists()
    assert db_path.exists()


def test_constructor_idempotent_on_existing_schema(tmp_path: Path) -> None:
    """Reopening the same DB path is a no-op for the schema (alembic
    upgrade head finds nothing to do). No exception."""
    db_path = tmp_path / "instinct.db"
    SQLAlchemyObservationStore(db_path)
    SQLAlchemyObservationStore(db_path)


def test_pragmas_applied_on_connect(tmp_path: Path) -> None:
    """journal_mode=WAL and synchronous=NORMAL applied per arch §8.3."""
    db_path = tmp_path / "instinct.db"
    store = SQLAlchemyObservationStore(db_path)
    with store._engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        synchronous = conn.execute(text("PRAGMA synchronous")).scalar()
    assert str(journal_mode).lower() == "wal"
    # synchronous=NORMAL is integer 1 in SQLite
    assert int(synchronous) == 1


# ---------- begin_run ----------


def test_begin_run_returns_int_id(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())
    assert isinstance(run_id, int)
    assert run_id > 0


def test_begin_run_inserts_row_with_running_status(tmp_path: Path) -> None:
    db_path = tmp_path / "instinct.db"
    store = SQLAlchemyObservationStore(db_path)
    run_id = store.begin_run(_meta(notes="hello"))

    with store._engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, notes, completed_at FROM runs WHERE id = :id"),
            {"id": run_id},
        ).fetchone()
    assert row is not None
    assert row[0] == RunStatus.RUNNING.value
    assert row[1] == "hello"
    assert row[2] is None


def test_begin_run_persists_metadata_fields(tmp_path: Path) -> None:
    """Repo fingerprint, source label, config hash, tool/metric versions
    all round-trip from RunMeta into the row."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    meta = _meta(
        repo_fingerprint="fp_specific",
        repo_fingerprint_source=RepoFingerprintSource.FIRST_COMMIT,
        commit_sha="abc123",
        branch="main",
        config_hash="cfg_hash_value",
        tool_version="9.9.9",
        metric_version="mv_zzz",
    )
    run_id = store.begin_run(meta)

    with store._engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT repo_fingerprint, repo_fingerprint_source, commit_sha, "
                "branch, config_hash, tool_version, metric_version "
                "FROM runs WHERE id = :id"
            ),
            {"id": run_id},
        ).fetchone()
    assert row == (
        "fp_specific",
        "first_commit",
        "abc123",
        "main",
        "cfg_hash_value",
        "9.9.9",
        "mv_zzz",
    )


def test_begin_run_distinct_ids_per_call(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    a = store.begin_run(_meta())
    b = store.begin_run(_meta())
    assert a != b


# ---------- complete_run ----------


def test_complete_run_updates_status_and_completed_at(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())
    store.complete_run(run_id, RunStatus.COMPLETED)

    with store._engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, completed_at FROM runs WHERE id = :id"),
            {"id": run_id},
        ).fetchone()
    assert row is not None
    assert row[0] == RunStatus.COMPLETED.value
    assert row[1] is not None  # completed_at populated


def test_complete_run_with_failed_status(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())
    store.complete_run(run_id, RunStatus.FAILED)

    with store._engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM runs WHERE id = :id"), {"id": run_id}
        ).scalar()
    assert status == RunStatus.FAILED.value


def test_complete_run_idempotent(tmp_path: Path) -> None:
    """Calling twice doesn't raise; final state is the second call's status."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())
    store.complete_run(run_id, RunStatus.COMPLETED)
    store.complete_run(run_id, RunStatus.FAILED)

    with store._engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM runs WHERE id = :id"), {"id": run_id}
        ).scalar()
    assert status == RunStatus.FAILED.value


# ---------- upsert_artifact ----------


def _artifact(ast_hash: str = "ah_alpha", **overrides: object) -> Artifact:
    base = {
        "ast_hash": ast_hash,
        "language": Language.PYTHON,
        "kind": ArtifactKind.FUNCTION,
        "name": "f",
        "enclosing_scope": None,
        "source_range": SourceRange(file_path="x.py", line_start=1, line_end=10),
    }
    base.update(overrides)
    return Artifact(**base)  # type: ignore[arg-type]


def _metric(metric_id: str = "cyclomatic_complexity", value: float | int = 3) -> MetricValue:
    return MetricValue(
        metric_id=metric_id,
        value=value,
        metric_version="1.2.0",
        confidence=Confidence.HIGH,
    )


def _location(**overrides: object) -> FileLocation:
    base = {
        "file_path": "src/foo.py",
        "line_start": 1,
        "line_end": 10,
        "symbol_name": "f",
        "enclosing_scope": None,
        "context_hash": "ctx_" + "a" * 60,
    }
    base.update(overrides)
    return FileLocation(**base)  # type: ignore[arg-type]


def test_upsert_artifact_insert_returns_id_and_creates_row(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())

    artifact_id = store.upsert_artifact(run_id, _artifact(), [_metric()])
    assert isinstance(artifact_id, int)
    assert artifact_id > 0

    with store._engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT ast_hash, language, artifact_kind, occurrence_count, "
                "stability_tier, first_seen_run_id, last_seen_run_id "
                "FROM observation_artifacts WHERE id = :id"
            ),
            {"id": artifact_id},
        ).fetchone()
    assert row == ("ah_alpha", "python", "function", 1, "volatile", run_id, run_id)


def test_upsert_artifact_persists_metrics_json(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())

    artifact_id = store.upsert_artifact(
        run_id,
        _artifact(),
        [
            _metric("cyclomatic_complexity", 4),
            _metric("cognitive_complexity", 2),
        ],
    )

    with store._engine.connect() as conn:
        raw = conn.execute(
            text("SELECT metrics_json FROM observation_artifacts WHERE id = :id"),
            {"id": artifact_id},
        ).scalar_one()
    parsed = json.loads(raw)
    assert parsed["cyclomatic_complexity"]["value"] == 4
    assert parsed["cyclomatic_complexity"]["confidence"] == "high"
    assert parsed["cognitive_complexity"]["value"] == 2


def test_upsert_artifact_dedupes_on_repeat_within_same_run(tmp_path: Path) -> None:
    """Calling upsert twice with the same ast_hash returns the same id
    and increments occurrence_count."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())

    a = store.upsert_artifact(run_id, _artifact(), [_metric()])
    b = store.upsert_artifact(run_id, _artifact(), [_metric()])
    assert a == b

    with store._engine.connect() as conn:
        count = conn.execute(
            text("SELECT occurrence_count FROM observation_artifacts WHERE id = :id"),
            {"id": a},
        ).scalar_one()
    assert count == 2


def test_upsert_artifact_dedupes_across_runs(tmp_path: Path) -> None:
    """Same artifact in two consecutive runs reuses the row, bumps
    last_seen_run_id, and leaves first_seen_run_id stable."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")

    run_a = store.begin_run(_meta())
    artifact_id = store.upsert_artifact(run_a, _artifact(), [_metric()])
    store.complete_run(run_a, RunStatus.COMPLETED)

    run_b = store.begin_run(_meta())
    same_id = store.upsert_artifact(run_b, _artifact(), [_metric()])
    assert same_id == artifact_id

    with store._engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT first_seen_run_id, last_seen_run_id, occurrence_count, "
                "stability_tier FROM observation_artifacts WHERE id = :id"
            ),
            {"id": artifact_id},
        ).fetchone()
    assert row == (run_a, run_b, 2, "settled")


def test_upsert_artifact_distinct_ast_hashes_get_distinct_rows(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())

    a = store.upsert_artifact(run_id, _artifact(ast_hash="ah_a"), [_metric()])
    b = store.upsert_artifact(run_id, _artifact(ast_hash="ah_b"), [_metric()])
    assert a != b


def test_upsert_artifact_metric_version_change_creates_new_row(tmp_path: Path) -> None:
    """Different combined metric_version → different dedup key →
    two distinct artifact rows for the same ast_hash. This is the
    intended invalidation behaviour when a metric is added or bumped."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")

    meta_v1 = _meta(metric_version="mv_v1aaaaaaaa")
    run_v1 = store.begin_run(meta_v1)
    a = store.upsert_artifact(run_v1, _artifact(), [_metric()])

    meta_v2 = _meta(metric_version="mv_v2bbbbbbbb")
    run_v2 = store.begin_run(meta_v2)
    b = store.upsert_artifact(run_v2, _artifact(), [_metric()])

    assert a != b


def test_upsert_artifact_unknown_run_id_raises(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(LookupError, match="run_id"):
        store.upsert_artifact(99999, _artifact(), [_metric()])


def test_upsert_artifact_repo_fingerprint_inherited_from_run(tmp_path: Path) -> None:
    """The artifact row's repo_fingerprint comes from the run, not the
    Artifact instance — keeps cross-repo aggregation in the warehouse
    correct without requiring callers to thread the value."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta(repo_fingerprint="fp_specific"))
    artifact_id = store.upsert_artifact(run_id, _artifact(), [_metric()])

    with store._engine.connect() as conn:
        fp = conn.execute(
            text("SELECT repo_fingerprint FROM observation_artifacts WHERE id = :id"),
            {"id": artifact_id},
        ).scalar_one()
    assert fp == "fp_specific"


# ---------- record_observation ----------


def test_record_observation_inserts_row(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())
    artifact_id = store.upsert_artifact(run_id, _artifact(), [_metric()])

    store.record_observation(
        run_id,
        artifact_id,
        _location(file_path="src/foo.py", symbol_name="f", line_start=10, line_end=20),
    )

    with store._engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT run_id, artifact_id, file_path, line_start, line_end, "
                "symbol_name, enclosing_scope, context_hash FROM run_observations "
                "WHERE run_id = :rid AND artifact_id = :aid"
            ),
            {"rid": run_id, "aid": artifact_id},
        ).fetchone()
    assert row is not None
    assert row[0] == run_id
    assert row[1] == artifact_id
    assert row[2] == "src/foo.py"
    assert row[3] == 10
    assert row[4] == 20
    assert row[5] == "f"
    assert row[6] is None
    assert row[7].startswith("ctx_")


def test_record_observation_allows_multiple_per_artifact_per_run(tmp_path: Path) -> None:
    """Same artifact at two different file locations in one run produces
    two run_observations rows."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    run_id = store.begin_run(_meta())
    artifact_id = store.upsert_artifact(run_id, _artifact(), [_metric()])

    store.record_observation(run_id, artifact_id, _location(file_path="a.py"))
    store.record_observation(run_id, artifact_id, _location(file_path="b.py"))

    with store._engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM run_observations WHERE run_id = :rid AND artifact_id = :aid"
            ),
            {"rid": run_id, "aid": artifact_id},
        ).scalar_one()
    assert count == 2


# ---------- not-yet-implemented stubs (Slice 6) ----------


def test_write_ranking_raises_not_implemented(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(NotImplementedError, match="Slice 6"):
        store.write_ranking(1, None)  # type: ignore[arg-type]


def test_write_profile_raises_not_implemented(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(NotImplementedError, match="Slice 6"):
        store.write_profile(1, None)  # type: ignore[arg-type]
