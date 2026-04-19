"""Tests for analyze.rules — cognitive rules YAML loader."""

from __future__ import annotations

import pytest

from savviety_instinct.analyze.rules import CognitiveIncrement, load_cognitive_rules
from savviety_instinct.core.types import Language
from savviety_instinct.parse.types import ControlFlowNodeKind


def test_load_python_rules_succeeds() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    assert rules.language == Language.PYTHON


def test_rules_include_every_kind() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    for kind in ControlFlowNodeKind:
        assert kind in rules.increments, f"Missing rule for {kind}"


def test_if_rule_structure() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    if_rule = rules.increments[ControlFlowNodeKind.IF]
    assert isinstance(if_rule, CognitiveIncrement)
    assert if_rule.base == 1
    assert if_rule.increments_nesting is True


def test_else_does_not_nest() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    else_rule = rules.increments[ControlFlowNodeKind.ELSE]
    assert else_rule.base == 1
    assert else_rule.increments_nesting is False


def test_try_has_zero_base_but_nests() -> None:
    """try itself is +0 (wrapper) but nests its except clauses."""
    rules = load_cognitive_rules(Language.PYTHON)
    try_rule = rules.increments[ControlFlowNodeKind.TRY]
    assert try_rule.base == 0
    assert try_rule.increments_nesting is True


def test_load_is_cached() -> None:
    a = load_cognitive_rules(Language.PYTHON)
    b = load_cognitive_rules(Language.PYTHON)
    assert a is b  # same object returned from lru_cache


def test_load_unsupported_language_raises() -> None:
    with pytest.raises(ValueError, match="No cognitive rules YAML for"):
        load_cognitive_rules(Language.RUST)
