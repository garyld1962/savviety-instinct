"""Tests for savviety_instinct.config.loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from savviety_instinct.config.loader import (
    ConfigFileError,
    load_config,
    save_config,
    scaffold_default_config,
)
from savviety_instinct.config.models import InstinctConfig, Scope


def test_scaffold_writes_valid_yaml_with_scope(tmp_path: Path):
    target = tmp_path / "config.yaml"
    scaffold_default_config(target)
    assert target.exists()
    data = yaml.safe_load(target.read_text())
    assert data["scope"] == "personal"
    # Full optional block present per HANDOFF.
    assert "sync_allowed" in data
    assert "remote_apis_allowed" in data
    assert "include_in_cross_project" in data
    assert "llm_backend" in data
    assert "assist_level" in data


def test_scaffold_is_loadable_back_into_config(tmp_path: Path):
    target = tmp_path / "config.yaml"
    scaffold_default_config(target)
    cfg = load_config(target)
    assert cfg.scope == Scope.PERSONAL
    assert cfg.sync_allowed is False


def test_scaffold_refuses_to_overwrite(tmp_path: Path):
    target = tmp_path / "config.yaml"
    target.write_text("scope: corporate\n")
    with pytest.raises(ConfigFileError):
        scaffold_default_config(target)
    # Original content untouched.
    assert target.read_text() == "scope: corporate\n"


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(ConfigFileError):
        load_config(tmp_path / "nope.yaml")


def test_load_invalid_yaml_raises(tmp_path: Path):
    target = tmp_path / "config.yaml"
    target.write_text(": : :\n")
    with pytest.raises(ConfigFileError):
        load_config(target)


def test_load_missing_scope_raises(tmp_path: Path):
    target = tmp_path / "config.yaml"
    target.write_text("sync_allowed: false\n")
    with pytest.raises(ConfigFileError) as exc:
        load_config(target)
    assert "scope" in str(exc.value).lower()


def test_save_and_load_roundtrip(tmp_path: Path):
    target = tmp_path / "config.yaml"
    cfg = InstinctConfig(scope=Scope.PERSONAL)
    save_config(cfg, target)
    loaded = load_config(target)
    assert loaded == cfg
