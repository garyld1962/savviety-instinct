"""Tests for repo_fingerprint derivation per D10."""

from __future__ import annotations

import hashlib
import socket
import subprocess
from pathlib import Path

import pytest

from savviety_instinct.storage.fingerprint import derive_repo_fingerprint
from savviety_instinct.storage.interfaces import RepoFingerprintSource


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _init_git_repo(path: Path) -> None:
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _git_capture(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_fingerprint_from_first_commit_sha(tmp_path: Path) -> None:
    """Tier 1: a real commit produces a FIRST_COMMIT fingerprint that
    matches the SHA-256 of the root commit's hash."""
    _init_git_repo(tmp_path)
    (tmp_path / "f.txt").write_text("hello")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-m", "init")
    root_sha = _git_capture(tmp_path, "rev-parse", "HEAD")

    fingerprint, source = derive_repo_fingerprint(tmp_path)

    assert source is RepoFingerprintSource.FIRST_COMMIT
    assert fingerprint == _sha256(root_sha)


def test_fingerprint_falls_back_to_origin_url(tmp_path: Path) -> None:
    """Tier 2: an initialized repo with a remote but no commits derives
    fingerprint from the origin URL."""
    _init_git_repo(tmp_path)
    _git(tmp_path, "remote", "add", "origin", "https://example.com/foo.git")
    # Deliberately no commits.

    fingerprint, source = derive_repo_fingerprint(tmp_path)

    assert source is RepoFingerprintSource.ORIGIN_URL
    assert fingerprint == _sha256("https://example.com/foo.git")


def test_fingerprint_synthetic_for_non_git_directory(tmp_path: Path) -> None:
    """Tier 3: a plain directory with no .git derives a synthetic
    fingerprint from hostname + absolute path."""
    fingerprint, source = derive_repo_fingerprint(tmp_path)

    expected = _sha256(f"{socket.gethostname()}:{tmp_path.resolve()}")
    assert source is RepoFingerprintSource.SYNTHETIC
    assert fingerprint == expected


def test_fingerprint_is_stable_across_calls(tmp_path: Path) -> None:
    """Two calls in a row produce identical results — no clock or random
    inputs in any tier."""
    _init_git_repo(tmp_path)
    (tmp_path / "f.txt").write_text("hello")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-m", "init")

    a = derive_repo_fingerprint(tmp_path)
    b = derive_repo_fingerprint(tmp_path)
    assert a == b


def test_fingerprint_differs_per_repo(tmp_path: Path) -> None:
    """Two unrelated repos produce different fingerprints."""
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    for d in (a_dir, b_dir):
        _init_git_repo(d)
        (d / "f.txt").write_text(d.name)
        _git(d, "add", "f.txt")
        _git(d, "commit", "-m", "init")

    a_fp, _ = derive_repo_fingerprint(a_dir)
    b_fp, _ = derive_repo_fingerprint(b_dir)
    assert a_fp != b_fp


def test_fingerprint_synthetic_differs_per_path(tmp_path: Path) -> None:
    """Two non-git dirs at different paths get different synthetic
    fingerprints."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()

    a_fp, a_src = derive_repo_fingerprint(a)
    b_fp, b_src = derive_repo_fingerprint(b)

    assert a_src is RepoFingerprintSource.SYNTHETIC
    assert b_src is RepoFingerprintSource.SYNTHETIC
    assert a_fp != b_fp


def test_fingerprint_when_git_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If `git` isn't on PATH at all, fall through to synthetic."""
    monkeypatch.setenv("PATH", "")
    fingerprint, source = derive_repo_fingerprint(tmp_path)
    assert source is RepoFingerprintSource.SYNTHETIC
    assert fingerprint == _sha256(f"{socket.gethostname()}:{tmp_path.resolve()}")
