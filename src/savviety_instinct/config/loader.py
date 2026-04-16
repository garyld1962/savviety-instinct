"""YAML loading, saving, and scaffolding for .instinct/config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from savviety_instinct.config.models import InstinctConfig

DEFAULT_CONFIG_YAML = """\
# Instinct per-repo configuration.
# See docs/04-architecture-spec.md §6 for the full reference.

# REQUIRED — explicit scope declaration (D8).
# Valid values: personal | corporate | open-source
scope: personal

# Storage / network flags (all default to false).
# For scope: corporate, these MUST stay false (D5 / D8 / D10).
sync_allowed: false             # R2+ push to Postgres warehouse (D10)
remote_apis_allowed: false      # D5 hard guarantee
include_in_cross_project: false # D8 hard guarantee

# LLM backend (MVP: always disabled; R2+ adds local | ollama | anthropic).
llm_backend: disabled

# Assist level (MVP: only 'observe' is valid; R4 adds suggest | patch_assist | apply).
assist_level: observe
"""


class ConfigFileError(Exception):
    """Wraps any failure to read, parse, or validate a config file."""


def scaffold_default_config(path: Path) -> None:
    """Write the default config template to `path`.

    Refuses to overwrite an existing file.
    """
    if path.exists():
        raise ConfigFileError(f"Config already exists at {path}; refusing to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_YAML)


def load_config(path: Path) -> InstinctConfig:
    """Load and validate config from `path`.

    Raises ConfigFileError on any failure (missing file, invalid YAML,
    or Pydantic validation error). Validation errors include the list of
    field issues so a user can fix them.
    """
    if not path.exists():
        raise ConfigFileError(f"Config file not found: {path}")
    try:
        raw = path.read_text()
    except OSError as e:
        raise ConfigFileError(f"Failed to read {path}: {e}") from e
    try:
        data: Any = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigFileError(f"Invalid YAML in {path}: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigFileError(
            f"Config root must be a mapping in {path}; got {type(data).__name__}."
        )
    try:
        return InstinctConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigFileError(f"Invalid config in {path}:\n{e}") from e


def save_config(config: InstinctConfig, path: Path) -> None:
    """Serialize `config` to YAML at `path` (overwrites)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, sort_keys=False))
