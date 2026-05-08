"""Per-run metadata helpers populated at run start.

`compute_config_hash` and `compute_combined_metric_version` produce the
two derived hashes written to `runs.config_hash` and
`runs.metric_version`. `derive_git_commit_branch` reads the analyzed
repo's HEAD (cwd) for `runs.commit_sha` and `runs.branch`.

Per Slice 5 Scope #2: `combined_metric_version` is the single dedup key
for `observation_artifacts.(ast_hash, language, metric_version)` —
adding or removing a metric changes the combined hash, naturally
invalidating all prior artifacts at the previous version.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import Metric
from savviety_instinct.storage._git import git_capture


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_config_hash(config: InstinctConfig) -> str:
    """Stable hash of the loaded config. Pydantic's `model_dump_json`
    output is deterministic given the model's field order."""
    return _sha256(config.model_dump_json())


def compute_combined_metric_version(metrics: Iterable[Metric]) -> str:
    """Compact hash of the registered metrics' (id, version) pairs.

    Format: `mv_<first 12 hex of sha256(sorted "id:version" pairs joined by "|")>`.
    Sorting makes the hash insensitive to registration order. Adding,
    removing, or bumping any individual metric version produces a new
    combined version, naturally invalidating prior `observation_artifacts`
    rows under the old combined hash.
    """
    pairs = sorted(f"{m.id}:{m.version}" for m in metrics)
    joined = "|".join(pairs)
    return f"mv_{_sha256(joined)[:12]}"


def derive_git_commit_branch(cwd: Path) -> tuple[str | None, str | None]:
    """Return (commit_sha, branch_name) from `cwd` git, or (None, None)
    if not in a git repo or the lookups fail. `branch` is None on a
    detached HEAD even when `commit_sha` is populated."""
    commit = git_capture(cwd, ["rev-parse", "HEAD"])
    branch = git_capture(cwd, ["symbolic-ref", "--short", "HEAD"])
    return commit, branch
