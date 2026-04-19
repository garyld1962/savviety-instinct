"""Tests for parse.adapter — Protocol conformance and dispatch."""

from __future__ import annotations

import pytest

from savviety_instinct.core.types import Language
from savviety_instinct.parse.adapter import LanguageAdapter, get_adapter


def test_get_adapter_python_returns_adapter() -> None:
    adapter = get_adapter(Language.PYTHON)
    assert isinstance(adapter, LanguageAdapter)


def test_get_adapter_unsupported_language_raises() -> None:
    with pytest.raises(ValueError, match="No adapter registered for"):
        get_adapter(Language.RUST)


def test_get_adapter_is_idempotent() -> None:
    """Adapter instances are memoized at module load; successive calls return same object."""
    a = get_adapter(Language.PYTHON)
    b = get_adapter(Language.PYTHON)
    assert a is b
