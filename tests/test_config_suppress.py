"""Tests for the `suppress` field on the config model."""

from __future__ import annotations

import pytest

from savviety_instinct.config.models import InstinctConfig

DEFAULTS_EXPECTED = {
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/migrations/**",
    "**/__pycache__/**",
    "**/.venv/**",
    "**/build/**",
    "**/dist/**",
    "**/conftest.py",
}


def test_suppress_defaults_include_tests_and_migrations() -> None:
    cfg = InstinctConfig(scope="personal")
    assert set(cfg.suppress) == DEFAULTS_EXPECTED


def test_suppress_can_be_overridden() -> None:
    cfg = InstinctConfig(scope="personal", suppress=["foo/**"])
    assert cfg.suppress == ["foo/**"]


def test_suppress_empty_list_is_allowed() -> None:
    """User can opt out of all suppressions by setting suppress: []."""
    cfg = InstinctConfig(scope="personal", suppress=[])
    assert cfg.suppress == []


def test_suppress_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        InstinctConfig(scope="personal", suppress=[123])  # type: ignore[list-item]
