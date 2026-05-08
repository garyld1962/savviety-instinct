"""Repository fingerprint derivation per D10.

`repo_fingerprint` is a stable identifier for the repo containing the
analyzed code. It travels on every `runs` and `observation_artifacts`
row so the R2 Postgres warehouse can merge per-repo SQLite contents
without identity collisions.

Three derivation tiers (highest preference first):

1. **first_commit** — SHA-256 of the repo's first commit SHA. Survives
   clones, remote URL changes, and branch renames.
2. **origin_url** — SHA-256 of `git config --get remote.origin.url`.
   Used for fresh repos with a remote but no commits, or unusual cases
   where the first-commit lookup fails.
3. **synthetic** — SHA-256 of `<hostname>:<absolute path>`. Used for
   non-git workspaces. Per D10, the warehouse is expected to label
   these so cross-machine deduplication can reject them.

The source label is written to `runs.repo_fingerprint_source`.
"""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path

from savviety_instinct.storage._git import git_capture
from savviety_instinct.storage.interfaces import RepoFingerprintSource


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_repo_fingerprint(cwd: Path) -> tuple[str, RepoFingerprintSource]:
    """Compute the repo_fingerprint for the repo containing `cwd`.

    Returns (hex_digest, source_label). Always succeeds — the synthetic
    fallback covers any non-git directory.
    """
    # Tier 1: first-commit SHA. `--max-parents=0` returns root commits;
    # there's typically one. If multiple roots exist (merged unrelated
    # histories — rare), the first listed is used.
    root_commits = git_capture(cwd, ["log", "--max-parents=0", "--format=%H"])
    if root_commits:
        first_commit = root_commits.splitlines()[0]
        return _sha256(first_commit), RepoFingerprintSource.FIRST_COMMIT

    # Tier 2: origin URL.
    origin_url = git_capture(cwd, ["config", "--get", "remote.origin.url"])
    if origin_url:
        return _sha256(origin_url), RepoFingerprintSource.ORIGIN_URL

    # Tier 3: synthetic from hostname + absolute path.
    hostname = socket.gethostname()
    abs_path = str(cwd.resolve())
    return _sha256(f"{hostname}:{abs_path}"), RepoFingerprintSource.SYNTHETIC
