"""Git subprocess helpers internal to the storage package.

Underscore-prefixed module name signals "internal" — callers outside
`storage/` should not import from here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_capture(cwd: Path, args: list[str]) -> str | None:
    """Run a git subcommand in `cwd`. Return stripped stdout, or None on
    any error (non-zero exit, git missing, output empty)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None
