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


@app.command("run")
def run_cmd(
    path: Path = typer.Argument(  # noqa: B008
        ...,
        help="File or directory to analyze. Must be a .py file or a dir with .py files.",
    ),
) -> None:
    """Analyze Python code at PATH and print metrics to stdout.

    Slice 5: persists observations to `.instinct/instinct.db` per D10
    while preserving the Slice 3 stdout output. Re-runs short-circuit
    via the dormant-artifact shortcut (arch §8.2). Full report layer
    arrives in Slice 6.
    """
    from savviety_instinct.analyze import run_pipeline_with_persistence
    from savviety_instinct.config.loader import ConfigFileError, load_config
    from savviety_instinct.storage.sqlite_store import SQLAlchemyObservationStore

    cwd = Path.cwd()
    config_path = cwd / ".instinct" / "config.yaml"
    try:
        config = load_config(config_path)
    except ConfigFileError as e:
        typer.echo(f"Config error: {e}", err=True)
        raise typer.Exit(code=1) from e

    if not path.exists():
        typer.echo(f"Path not found: {path}", err=True)
        raise typer.Exit(code=2)

    db_path = cwd / ".instinct" / "instinct.db"
    store = SQLAlchemyObservationStore(db_path)
    results, summary = run_pipeline_with_persistence(path, config, store, cwd=cwd)
    rows = list(results)

    # Deterministic sort.
    rows.sort(
        key=lambda r: (
            r[0].source_range.file_path,
            r[0].source_range.line_start,
            r[0].name,
            r[1].metric_id,
        )
    )

    for artifact, metric_value in rows:
        sr = artifact.source_range
        qualified = (
            artifact.name
            if artifact.enclosing_scope is None
            else f"{artifact.enclosing_scope}.{artifact.name}"
        )
        typer.echo(
            f"{sr.file_path}:{sr.line_start}-{sr.line_end}\t"
            f"{qualified}\t"
            f"{metric_value.metric_id}={metric_value.value}\t"
            f"{metric_value.confidence.value}"
        )

    typer.echo(
        f"[summary] {summary.files_parsed} files parsed, "
        f"{summary.files_skipped} files skipped, "
        f"{summary.functions_analyzed} functions analyzed",
        err=True,
    )


_RESERVED_COMMAND_MESSAGE_FMT = (
    "Command '{cmd}' is not available in this release. "
    "See docs/04-architecture-spec.md §7 for the release roadmap."
)


def _reserved(cmd: str) -> None:
    typer.echo(_RESERVED_COMMAND_MESSAGE_FMT.format(cmd=cmd))
    raise typer.Exit(code=2)


@app.command("sync")
def sync_cmd() -> None:
    """Reserved (R2): push observations to the Postgres warehouse."""
    _reserved("sync")


@app.command("curate")
def curate_cmd() -> None:
    """Reserved (R3): pattern curation."""
    _reserved("curate")


@app.command("suggest")
def suggest_cmd() -> None:
    """Reserved (R4): suggestion generation."""
    _reserved("suggest")


@app.command("apply")
def apply_cmd() -> None:
    """Reserved (R4): apply suggested changes."""
    _reserved("apply")


@app.command("serve")
def serve_cmd() -> None:
    """Reserved (R5): MCP server."""
    _reserved("serve")
