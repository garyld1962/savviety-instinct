"""End-to-end Slice 5 re-run test (arch §10.4).

Two `instinct run` invocations against an unchanged fixture exercise
the dormant-artifact shortcut. Asserts:

- Two `runs` rows; both completed.
- `observation_artifacts` row count is unchanged between runs (dedup).
- Each artifact's `occurrence_count` is 2 after the second run, with
  `last_seen_run_id` advancing to run 2 and `stability_tier` settled.
- `run_observations` row count doubles (one fresh sighting per run).
- A compute-call spy on CYCLOMATIC_METRIC confirms the metric layer is
  NOT re-entered on the second run — proves the shortcut fires.

Performance assertions (NFR-7 ≤15s rerun) are NOT here; per Slice 5
Scope #20, those land in Slice 10 with reference-corpus benchmarks.
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


def _run_cli(sample: Path) -> None:
    result = CliRunner().invoke(app, ["run", str(sample)], catch_exceptions=False)
    assert result.exit_code == 0, result.output


# ---------- runs table ----------


def test_two_runs_produces_two_run_rows(scaffolded_repo: tuple[Path, Path]) -> None:
    repo_root, sample = scaffolded_repo
    _run_cli(sample)
    _run_cli(sample)
    rows = _query(repo_root / ".instinct" / "instinct.db", "SELECT id, status FROM runs")
    assert len(rows) == 2
    assert all(r[1] == "completed" for r in rows)


# ---------- artifact dedup ----------


def test_artifact_row_count_stable_across_runs(scaffolded_repo: tuple[Path, Path]) -> None:
    """Same source = same ast_hashes = no new artifact rows on the
    second run. This is the dedup guarantee that makes the warehouse
    aggregation cheap (D10)."""
    repo_root, sample = scaffolded_repo
    db = repo_root / ".instinct" / "instinct.db"

    _run_cli(sample)
    after_first = _query(db, "SELECT COUNT(*) FROM observation_artifacts")[0][0]

    _run_cli(sample)
    after_second = _query(db, "SELECT COUNT(*) FROM observation_artifacts")[0][0]

    assert after_first == after_second
    # Sanity: the count is non-zero (1 module + 2 functions = 3)
    assert after_first == 3


def test_artifact_occurrence_count_increments_on_second_run(
    scaffolded_repo: tuple[Path, Path],
) -> None:
    repo_root, sample = scaffolded_repo
    db = repo_root / ".instinct" / "instinct.db"

    _run_cli(sample)
    _run_cli(sample)

    rows = _query(db, "SELECT occurrence_count FROM observation_artifacts")
    assert all(r[0] == 2 for r in rows), rows


def test_artifact_last_seen_run_id_advances(scaffolded_repo: tuple[Path, Path]) -> None:
    """first_seen_run_id pinned to run 1; last_seen_run_id moves to
    run 2 on shortcut hit."""
    repo_root, sample = scaffolded_repo
    db = repo_root / ".instinct" / "instinct.db"

    _run_cli(sample)
    _run_cli(sample)

    rows = _query(
        db,
        "SELECT first_seen_run_id, last_seen_run_id FROM observation_artifacts",
    )
    for first_seen, last_seen in rows:
        assert first_seen == 1
        assert last_seen == 2


def test_stability_tier_transitions_to_settled(scaffolded_repo: tuple[Path, Path]) -> None:
    """Slice 5 Scope #3: occurrence_count >= 2 → stability_tier='settled'."""
    repo_root, sample = scaffolded_repo
    db = repo_root / ".instinct" / "instinct.db"

    _run_cli(sample)
    _run_cli(sample)

    rows = _query(db, "SELECT stability_tier FROM observation_artifacts")
    assert all(r[0] == "settled" for r in rows), rows


# ---------- run_observations link table ----------


def test_observations_doubled_after_two_runs(scaffolded_repo: tuple[Path, Path]) -> None:
    """Each run gets a fresh batch of run_observations rows (one per
    artifact sighting). Two runs → twice the observations."""
    repo_root, sample = scaffolded_repo
    db = repo_root / ".instinct" / "instinct.db"

    _run_cli(sample)
    after_first = _query(db, "SELECT COUNT(*) FROM run_observations")[0][0]

    _run_cli(sample)
    after_second = _query(db, "SELECT COUNT(*) FROM run_observations")[0][0]

    assert after_second == after_first * 2
    # Sanity: 3 artifacts × 2 runs = 6
    assert after_second == 6


def test_observations_partition_by_run(scaffolded_repo: tuple[Path, Path]) -> None:
    """Each run's observations point to its own run_id."""
    repo_root, sample = scaffolded_repo
    db = repo_root / ".instinct" / "instinct.db"

    _run_cli(sample)
    _run_cli(sample)

    by_run = _query(
        db,
        "SELECT run_id, COUNT(*) FROM run_observations GROUP BY run_id ORDER BY run_id",
    )
    assert by_run == [(1, 3), (2, 3)]


# ---------- shortcut spy ----------


def test_second_run_skips_metric_computation(
    scaffolded_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin the dormant-shortcut behaviour: monkeypatch CYCLOMATIC_METRIC's
    compute to count invocations. The first run must call it (cold
    path); the second run must NOT (shortcut path)."""
    from savviety_instinct.analyze import CYCLOMATIC_METRIC

    _, sample = scaffolded_repo
    call_count = 0
    original = CYCLOMATIC_METRIC.compute

    def counting_compute(artifact, context):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return original(artifact, context)

    monkeypatch.setattr(CYCLOMATIC_METRIC, "compute", counting_compute)

    _run_cli(sample)
    after_first = call_count
    assert after_first == 2, (
        f"first run should compute cyclomatic for each of the 2 functions, got {after_first}"
    )

    _run_cli(sample)
    after_second = call_count - after_first
    assert after_second == 0, (
        f"second run should hit the dormant shortcut for every artifact, but cyclomatic.compute was called {after_second} times"
    )
