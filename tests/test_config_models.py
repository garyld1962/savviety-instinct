"""Tests for savviety_instinct.config.models (D5, D8, D10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from savviety_instinct.config.models import (
    AssistLevel,
    InstinctConfig,
    LlmBackend,
    Scope,
)


def test_scope_values():
    assert Scope.PERSONAL.value == "personal"
    assert Scope.CORPORATE.value == "corporate"
    assert Scope.OPEN_SOURCE.value == "open-source"


def test_assist_level_values():
    assert {a.value for a in AssistLevel} == {
        "observe",
        "suggest",
        "patch_assist",
        "apply",
    }


def test_llm_backend_values():
    assert {b.value for b in LlmBackend} == {
        "disabled",
        "local",
        "ollama",
        "anthropic",
    }


def test_scope_required():
    # Missing scope is a config error (FR-25, D8).
    with pytest.raises(ValidationError) as exc:
        InstinctConfig.model_validate({})
    assert "scope" in str(exc.value).lower()


def test_minimal_config_with_scope_only():
    cfg = InstinctConfig.model_validate({"scope": "personal"})
    assert cfg.scope == Scope.PERSONAL
    assert cfg.sync_allowed is False
    assert cfg.remote_apis_allowed is False
    assert cfg.include_in_cross_project is False
    assert cfg.assist_level == AssistLevel.OBSERVE
    assert cfg.llm_backend == LlmBackend.DISABLED


def test_assist_level_non_observe_rejected_in_mvp():
    # R4 hook: only "observe" is valid in MVP.
    with pytest.raises(ValidationError) as exc:
        InstinctConfig.model_validate({"scope": "personal", "assist_level": "suggest"})
    assert "observe" in str(exc.value).lower()


def test_corporate_forces_sync_allowed_false():
    # D10: scope=corporate must hard-false sync_allowed.
    with pytest.raises(ValidationError) as exc:
        InstinctConfig.model_validate(
            {"scope": "corporate", "sync_allowed": True}
        )
    assert "corporate" in str(exc.value).lower()


def test_corporate_forces_remote_apis_false():
    # D5/D8: corporate must hard-false remote_apis_allowed.
    with pytest.raises(ValidationError) as exc:
        InstinctConfig.model_validate(
            {"scope": "corporate", "remote_apis_allowed": True}
        )
    assert "corporate" in str(exc.value).lower()


def test_corporate_forces_include_in_cross_project_false():
    with pytest.raises(ValidationError) as exc:
        InstinctConfig.model_validate(
            {"scope": "corporate", "include_in_cross_project": True}
        )
    assert "corporate" in str(exc.value).lower()


def test_corporate_rejects_anthropic_llm_backend():
    # D5 hard guarantee: corporate code must not call out to remote APIs.
    with pytest.raises(ValidationError) as exc:
        InstinctConfig.model_validate(
            {"scope": "corporate", "llm_backend": "anthropic"}
        )
    assert "corporate" in str(exc.value).lower()
    assert "anthropic" in str(exc.value).lower()


def test_corporate_allows_local_llm_backends():
    for backend in ("disabled", "local", "ollama"):
        cfg = InstinctConfig.model_validate(
            {"scope": "corporate", "llm_backend": backend}
        )
        assert cfg.llm_backend.value == backend


def test_corporate_with_all_safe_defaults_is_accepted():
    cfg = InstinctConfig.model_validate({"scope": "corporate"})
    assert cfg.scope == Scope.CORPORATE
    # All D5/D8/D10 guarded fields default to false; this is the "safe" corporate config.
    assert cfg.sync_allowed is False
    assert cfg.remote_apis_allowed is False
    assert cfg.include_in_cross_project is False
    assert cfg.llm_backend.value == "disabled"


def test_unknown_keys_rejected():
    # arch §16.5: unknown keys are errors by default (strict).
    with pytest.raises(ValidationError):
        InstinctConfig.model_validate(
            {"scope": "personal", "not_a_real_key": "boom"}
        )
