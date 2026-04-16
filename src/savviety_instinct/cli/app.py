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

import typer

from savviety_instinct import __version__

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
