"""Instinct CLI (Typer).

Slice 1 surface:
    instinct version   — print tool and metric versions
    instinct init      — scaffold .instinct/config.yaml and .gitignore entries
    instinct sync      — R2 reserved; prints "not available in this release"
    instinct curate    — R3 reserved
    instinct suggest   — R4 reserved
    instinct apply     — R4 reserved
    instinct serve     — R5 reserved (MCP)

MVP commands that are not yet implemented in this slice (`run`, `report`,
`explain`, `trend`, `vacuum`, `rebuild-db`) are intentionally NOT registered;
Typer's default unknown-command error is sufficient.
"""

from __future__ import annotations

from pathlib import Path

import typer

from savviety_instinct import __version__
from savviety_instinct.config.loader import (
    ConfigFileError,
    scaffold_default_config,
)

app = typer.Typer(
    name="instinct",
    help="Instinct — measure what matters. Learn what your team does well. Apply it.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _callback() -> None:
    """Instinct — measure what matters. Learn what your team does well. Apply it."""


# Slice 1 has no registered metrics. Later slices append to this dict as
# they register their metrics (metric_id -> metric_version).
REGISTERED_METRIC_VERSIONS: dict[str, str] = {}


@app.command("version")
def version_cmd() -> None:
    """Print tool and metric versions."""
    typer.echo(f"instinct {__version__}")
    if REGISTERED_METRIC_VERSIONS:
        typer.echo("metrics:")
        for metric_id, version in sorted(REGISTERED_METRIC_VERSIONS.items()):
            typer.echo(f"  {metric_id}: {version}")
    else:
        typer.echo("metrics: (none registered)")


GITIGNORE_ENTRIES: tuple[str, ...] = (
    ".instinct/instinct.db",
    ".instinct/reports/",
)


def _ensure_gitignore_entries(gitignore_path: Path, entries: tuple[str, ...]) -> None:
    """Append each entry to .gitignore if not already present. Creates file if missing."""
    existing = gitignore_path.read_text() if gitignore_path.exists() else ""
    existing_lines = {line.strip() for line in existing.splitlines()}
    missing = [e for e in entries if e not in existing_lines]
    if not missing:
        return
    # Ensure a trailing newline before appending.
    if existing and not existing.endswith("\n"):
        existing += "\n"
    appended = existing + "\n".join(missing) + "\n"
    gitignore_path.write_text(appended)


@app.command("init")
def init_cmd() -> None:
    """Scaffold .instinct/config.yaml and add runtime paths to .gitignore."""
    cwd = Path.cwd()
    config_path = cwd / ".instinct" / "config.yaml"
    try:
        scaffold_default_config(config_path)
    except ConfigFileError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from e
    _ensure_gitignore_entries(cwd / ".gitignore", GITIGNORE_ENTRIES)
    typer.echo(f"Scaffolded {config_path.relative_to(cwd)}")
    typer.echo("Updated .gitignore with Instinct runtime paths.")
