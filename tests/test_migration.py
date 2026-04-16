"""Tests for the initial schema migration (arch §4.1)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture()
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Apply the initial migration to a fresh SQLite file and yield the URL."""

    db_path = tmp_path / "instinct.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("INSTINCT_DB_URL", url)

    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return url


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    return set(inspect(engine).get_table_names())


def _indexes(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def _columns(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    return {col["name"] for col in inspect(engine).get_columns(table)}


def test_migration_creates_all_tables(migrated_db: str):
    tables = _tables(migrated_db)
    assert {
        "runs",
        "observation_artifacts",
        "run_observations",
        "rankings",
        "run_profiles",
        "llm_verdicts",
        "patterns",
        "pattern_evidence",
    }.issubset(tables)


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
    assert {"idx_artifacts_ast_hash", "idx_artifacts_stability", "idx_artifacts_fingerprint"}.issubset(
        art_idx
    )
    obs_idx = _indexes(migrated_db, "run_observations")
    assert {
        "idx_run_obs_run",
        "idx_run_obs_artifact",
        "idx_run_obs_file",
        "idx_run_obs_context",
    }.issubset(obs_idx)
    assert "idx_rankings_run" in _indexes(migrated_db, "rankings")


def test_pattern_tables_exist_empty(migrated_db: str):
    engine = create_engine(migrated_db)
    with engine.connect() as conn:
        from sqlalchemy import text

        patterns_count = conn.execute(text("SELECT COUNT(*) FROM patterns")).scalar()
        evidence_count = conn.execute(text("SELECT COUNT(*) FROM pattern_evidence")).scalar()
    assert patterns_count == 0
    assert evidence_count == 0
    _ = os.getenv  # keep import
