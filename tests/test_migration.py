"""Tests for the initial schema migration (arch §4.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _make_config(url: str) -> Config:
    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Apply the initial migration to a fresh SQLite file and yield the URL."""

    db_path = tmp_path / "instinct.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("INSTINCT_DB_URL", url)
    command.upgrade(_make_config(url), "head")
    return url


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _indexes(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {ix["name"] for ix in inspect(engine).get_indexes(table)}
    finally:
        engine.dispose()


def _columns(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    try:
        return {col["name"] for col in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


EXPECTED_TABLES = {
    "runs",
    "observation_artifacts",
    "run_observations",
    "rankings",
    "run_profiles",
    "llm_verdicts",
    "patterns",
    "pattern_evidence",
}


def test_migration_creates_all_tables(migrated_db: str):
    assert EXPECTED_TABLES.issubset(_tables(migrated_db))


def test_runs_has_repo_fingerprint_columns(migrated_db: str):
    cols = _columns(migrated_db, "runs")
    assert "repo_fingerprint" in cols
    assert "repo_fingerprint_source" in cols


def test_observation_artifacts_has_repo_fingerprint(migrated_db: str):
    cols = _columns(migrated_db, "observation_artifacts")
    assert "repo_fingerprint" in cols


def test_run_observations_has_context_hash(migrated_db: str):
    cols = _columns(migrated_db, "run_observations")
    assert "context_hash" in cols, "D6: dedicated context_hash column on run_observations"


def test_expected_indexes_exist(migrated_db: str):
    assert "idx_runs_fingerprint" in _indexes(migrated_db, "runs")
    art_idx = _indexes(migrated_db, "observation_artifacts")
    assert {
        "idx_artifacts_ast_hash",
        "idx_artifacts_stability",
        "idx_artifacts_fingerprint",
    }.issubset(art_idx)
    obs_idx = _indexes(migrated_db, "run_observations")
    assert {
        "idx_run_obs_run",
        "idx_run_obs_artifact",
        "idx_run_obs_file",
        "idx_run_obs_context",
    }.issubset(obs_idx)
    assert "idx_rankings_run" in _indexes(migrated_db, "rankings")


def test_forward_compat_tables_have_key_columns(migrated_db: str):
    """R2/R3 reserved tables must ship with the right shape (even though empty)."""
    llm_cols = _columns(migrated_db, "llm_verdicts")
    assert {"artifact_id", "context_hash", "model_id", "prompt_hash", "stage"}.issubset(
        llm_cols
    )
    patterns_cols = _columns(migrated_db, "patterns")
    assert {"pattern_id", "scope", "file_path", "lifecycle_state"}.issubset(patterns_cols)
    evidence_cols = _columns(migrated_db, "pattern_evidence")
    assert {"pattern_id", "artifact_id", "run_id", "relation"}.issubset(evidence_cols)


def test_downgrade_removes_all_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Round-trip: upgrade then downgrade must leave no tables behind."""
    db_path = tmp_path / "instinct.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("INSTINCT_DB_URL", url)
    cfg = _make_config(url)
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES.issubset(_tables(url))
    command.downgrade(cfg, "base")
    remaining = _tables(url)
    # Alembic leaves its own version table; everything else must be gone.
    assert remaining - {"alembic_version"} == set(), f"Tables left after downgrade: {remaining}"


def test_migrated_db_accepts_inserts(migrated_db: str):
    """Smoke test that the schema is usable (not just structurally present)."""
    engine = create_engine(migrated_db)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO runs (repo_fingerprint, repo_fingerprint_source, "
                    "started_at, config_hash, tool_version, metric_version, status) "
                    "VALUES ('fp', 'synthetic', '2026-04-16 12:00:00', 'c', '0.1.0', "
                    "'0.0.0-slice1', 'running')"
                )
            )
            row_id = conn.execute(text("SELECT id FROM runs WHERE repo_fingerprint='fp'")).scalar()
        assert row_id is not None
    finally:
        engine.dispose()
