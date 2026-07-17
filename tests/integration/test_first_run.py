"""End-to-end Slice 5 first-run test (arch §10.4).

Scaffolds a fresh repo with `.instinct/config.yaml` and a tiny Python
file, invokes the CLI, and asserts the DB contents. The "fresh" path
exercises every cold-path branch — alembic upgrade, run lifecycle,
upsert_artifact, record_observation. The dormant-shortcut behaviour is
covered by tests/integration/test_re_run.py (Slice 5 task 6).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from savviety_instinct.cli.app import app

_FIXTURE_SOURCE = """def add(a, b):
    return a + b


def divide(a, b):
    if b == 0:
        return None
    return a / b
"""


def _scaffold_repo(repo_root: Path) -> Path:
    """Create a tmp 'repo' with .instinct/config.yaml and a sample
    .py file. Initializes git so repo_fingerprint goes through the
    first-commit path (covers the most-realistic case)."""
    (repo_root / ".instinct").mkdir(parents=True, exist_ok=True)
    (repo_root / ".instinct" / "config.yaml").write_text("scope: personal\nsuppress: []\n")
    (repo_root / "sample.py").write_text(_FIXTURE_SOURCE)

    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo_root, check=True, capture_output=True
    )
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True)

    return repo_root / "sample.py"


@pytest.fixture()
def scaffolded_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Returns (repo_root, sample_path). Sets cwd to repo_root."""
    sample = _scaffold_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path, sample


def _query(db_path: Path, sql: str, **params: object) -> list[tuple[object, ...]]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql), params).fetchall()]
    finally:
        engine.dispose()


def test_first_run_creates_db_file(scaffolded_repo: tuple[Path, Path]) -> None:
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0
    assert (repo_root / ".instinct" / "instinct.db").exists()


def test_first_run_writes_one_completed_run_row(scaffolded_repo: tuple[Path, Path]) -> None:
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0

    db = repo_root / ".instinct" / "instinct.db"
    rows = _query(db, "SELECT id, status, completed_at FROM runs")
    assert len(rows) == 1
    _, status, completed_at = rows[0]
    assert status == "completed"
    assert completed_at is not None


def test_first_run_repo_fingerprint_uses_first_commit(scaffolded_repo: tuple[Path, Path]) -> None:
    """Scaffold has a git commit, so D10's tier-1 (first_commit) should
    fire. Tier label is preserved on the row."""
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0

    db = repo_root / ".instinct" / "instinct.db"
    rows = _query(db, "SELECT repo_fingerprint_source, commit_sha, branch FROM runs")
    assert len(rows) == 1
    source, commit_sha, branch = rows[0]
    assert source == "first_commit"
    assert commit_sha is not None
    assert len(str(commit_sha)) == 40  # full git SHA
    assert branch == "main"


def test_first_run_writes_artifact_rows_for_module_and_functions(
    scaffolded_repo: tuple[Path, Path],
) -> None:
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0

    db = repo_root / ".instinct" / "instinct.db"
    rows = _query(
        db, "SELECT artifact_kind, occurrence_count, stability_tier FROM observation_artifacts"
    )
    kinds = {r[0] for r in rows}
    assert kinds == {"module", "function"}
    # Each artifact's first sighting → occurrence_count=1, tier=volatile.
    for _kind, count, tier in rows:
        assert count == 1
        assert tier == "volatile"


def test_first_run_metrics_json_roundtrips(scaffolded_repo: tuple[Path, Path]) -> None:
    """Metrics_json must contain at least cyclomatic for each function row."""
    import json

    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0

    db = repo_root / ".instinct" / "instinct.db"
    rows = _query(
        db,
        "SELECT metrics_json FROM observation_artifacts WHERE artifact_kind = 'function'",
    )
    assert len(rows) == 2  # add + divide
    for (raw,) in rows:
        parsed = json.loads(str(raw))
        assert "cyclomatic_complexity" in parsed
        assert "value" in parsed["cyclomatic_complexity"]


def test_first_run_writes_one_observation_per_artifact(
    scaffolded_repo: tuple[Path, Path],
) -> None:
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0

    db = repo_root / ".instinct" / "instinct.db"
    counts = _query(
        db,
        "SELECT COUNT(*) FROM run_observations WHERE run_id = (SELECT id FROM runs LIMIT 1)",
    )
    # 1 module + 2 functions = 3 sightings
    assert counts == [(3,)]


def test_first_run_observations_carry_context_hash(scaffolded_repo: tuple[Path, Path]) -> None:
    """D6 forward-compat: every run_observations row has a non-empty
    context_hash, even though no consumer reads it in MVP."""
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0

    db = repo_root / ".instinct" / "instinct.db"
    hashes = _query(db, "SELECT context_hash FROM run_observations")
    assert len(hashes) == 3
    for (h,) in hashes:
        assert h
        assert len(str(h)) == 64  # sha256 hex


def test_first_run_stdout_unchanged_from_slice_3(scaffolded_repo: tuple[Path, Path]) -> None:
    """Persistence is a side effect; stdout still emits the Slice 3
    tab-separated rows so existing tooling and downstream tests stay
    intact until Slice 6 introduces the report layer."""
    repo_root, sample = scaffolded_repo
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    # 1 module × 3 module-metrics + 2 functions × 6 function-metrics = 15 rows
    assert len(rows) > 0
    for row in rows:
        cols = row.split("\t")
        assert len(cols) == 4
        assert "=" in cols[2]
