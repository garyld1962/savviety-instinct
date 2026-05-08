"""Tests for SQLAlchemyObservationStore — Slice 5 task 2 surface
(constructor schema upgrade, begin_run, complete_run)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from savviety_instinct.storage.interfaces import (
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


# ---------- not-yet-implemented stubs ----------


def test_upsert_artifact_raises_not_implemented(tmp_path: Path) -> None:
    """Stub keeps the Protocol shape; task 3 fills it in."""
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(NotImplementedError, match="task 3"):
        store.upsert_artifact(None, [])  # type: ignore[arg-type]


def test_record_observation_raises_not_implemented(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(NotImplementedError, match="task 3"):
        store.record_observation(1, 1, None)  # type: ignore[arg-type]


def test_write_ranking_raises_not_implemented(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(NotImplementedError, match="Slice 6"):
        store.write_ranking(1, None)  # type: ignore[arg-type]


def test_write_profile_raises_not_implemented(tmp_path: Path) -> None:
    store = SQLAlchemyObservationStore(tmp_path / "instinct.db")
    with pytest.raises(NotImplementedError, match="Slice 6"):
        store.write_profile(1, None)  # type: ignore[arg-type]
