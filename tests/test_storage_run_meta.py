"""Tests for run-meta helpers (config_hash, combined_metric_version,
git commit/branch lookup)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from savviety_instinct.config.models import InstinctConfig, Scope
from savviety_instinct.storage.run_meta import (
    compute_combined_metric_version,
    compute_config_hash,
    derive_git_commit_branch,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class _FakeMetric:
    """Test stand-in matching the Metric Protocol's id/version attributes."""

    def __init__(self, id: str, version: str) -> None:
        self.id = id
        self.version = version


def _make_config(scope: Scope = Scope.PERSONAL) -> InstinctConfig:
    return InstinctConfig(scope=scope)


# ---------- compute_config_hash ----------


def test_config_hash_is_stable() -> None:
    """Same config inputs → same hash."""
    a = compute_config_hash(_make_config())
    b = compute_config_hash(_make_config())
    assert a == b


def test_config_hash_differs_on_scope_change() -> None:
    """Changing a tracked field produces a different hash."""
    personal = compute_config_hash(_make_config(scope=Scope.PERSONAL))
    corporate = compute_config_hash(_make_config(scope=Scope.CORPORATE))
    assert personal != corporate


def test_config_hash_is_64_hex_chars() -> None:
    """SHA-256 hex digest is always 64 characters."""
    h = compute_config_hash(_make_config())
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ---------- compute_combined_metric_version ----------


def test_combined_metric_version_format() -> None:
    """Format is `mv_` + 12 hex chars."""
    metrics = [_FakeMetric("m_a", "1.0.0"), _FakeMetric("m_b", "2.0.0")]
    v = compute_combined_metric_version(metrics)
    assert v.startswith("mv_")
    assert len(v) == 3 + 12
    assert all(c in "0123456789abcdef" for c in v[3:])


def test_combined_metric_version_is_order_invariant() -> None:
    """Different registration order → same hash (sort_keys-equivalent)."""
    a = compute_combined_metric_version(
        [_FakeMetric("alpha", "1.0.0"), _FakeMetric("beta", "1.0.0")]
    )
    b = compute_combined_metric_version(
        [_FakeMetric("beta", "1.0.0"), _FakeMetric("alpha", "1.0.0")]
    )
    assert a == b


def test_combined_metric_version_changes_on_version_bump() -> None:
    """Bumping any metric's version changes the combined hash — the
    dedup invalidation property."""
    before = compute_combined_metric_version(
        [_FakeMetric("alpha", "1.0.0"), _FakeMetric("beta", "1.0.0")]
    )
    after = compute_combined_metric_version(
        [_FakeMetric("alpha", "1.1.0"), _FakeMetric("beta", "1.0.0")]
    )
    assert before != after


def test_combined_metric_version_changes_on_metric_addition() -> None:
    """Adding a new metric changes the combined hash."""
    before = compute_combined_metric_version([_FakeMetric("alpha", "1.0.0")])
    after = compute_combined_metric_version(
        [_FakeMetric("alpha", "1.0.0"), _FakeMetric("beta", "1.0.0")]
    )
    assert before != after


def test_combined_metric_version_empty_set() -> None:
    """Empty registry still produces a valid hash (degenerate case)."""
    v = compute_combined_metric_version([])
    assert v.startswith("mv_")
    assert len(v) == 3 + 12


# ---------- derive_git_commit_branch ----------


def test_derive_git_returns_none_outside_repo(tmp_path: Path) -> None:
    """Plain directory → (None, None)."""
    commit, branch = derive_git_commit_branch(tmp_path)
    assert commit is None
    assert branch is None


def test_derive_git_returns_commit_and_branch_in_repo(tmp_path: Path) -> None:
    """Initialized repo with a commit on `main` returns the SHA and 'main'."""
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "f.txt").write_text("hi")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-m", "init")

    commit, branch = derive_git_commit_branch(tmp_path)
    assert commit is not None
    assert len(commit) == 40  # full SHA
    assert branch == "main"


def test_derive_git_branch_none_on_detached_head(tmp_path: Path) -> None:
    """Detached HEAD: commit_sha set, branch is None."""
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "f.txt").write_text("hi")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-m", "init")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(tmp_path, "checkout", "--detach", sha)

    commit, branch = derive_git_commit_branch(tmp_path)
    assert commit == sha
    assert branch is None
