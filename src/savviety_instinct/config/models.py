"""Pydantic v2 config models for .instinct/config.yaml.

Decisions enforced:
- D5: corporate scope → remote_apis_allowed hard-false
- D8: scope is required; no default
- D10: corporate scope → sync_allowed hard-false;
       corporate scope → include_in_cross_project hard-false
- R4 hook: assist_level must be "observe" in MVP (any other value is a
  validation error)
- D5 (extended): corporate scope → llm_backend in {disabled, local, ollama}
  only; anthropic is rejected because it implies outbound API traffic.
- arch §16.5: unknown keys are rejected (extra="forbid")
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Scope(StrEnum):
    PERSONAL = "personal"
    CORPORATE = "corporate"
    OPEN_SOURCE = "open-source"


class AssistLevel(StrEnum):
    """Assist levels. Note: string values use underscore (e.g., ``patch_assist``)
    to match the Python attribute name. Scope uses a hyphen (``open-source``)
    because the term itself is hyphenated. The inconsistency is intentional —
    do not normalise both to the same style.
    """

    OBSERVE = "observe"
    SUGGEST = "suggest"
    PATCH_ASSIST = "patch_assist"
    APPLY = "apply"


class LlmBackend(StrEnum):
    DISABLED = "disabled"
    LOCAL = "local"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


class InstinctConfig(BaseModel):
    """Validated Instinct configuration.

    Required fields: `scope`. All others have safe defaults.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: Scope

    # D5 / D8 / D10 flags
    sync_allowed: bool = False
    remote_apis_allowed: bool = False
    include_in_cross_project: bool = False

    # R2+ / R4 reserved, validated in MVP
    llm_backend: LlmBackend = LlmBackend.DISABLED
    assist_level: AssistLevel = AssistLevel.OBSERVE

    suppress: list[str] = Field(
        default_factory=lambda: [
            "**/tests/**",
            "**/test_*.py",
            "**/*_test.py",
            "**/migrations/**",
            "**/__pycache__/**",
            "**/.venv/**",
            "**/build/**",
            "**/dist/**",
            "**/conftest.py",
        ],
        description="Glob patterns of files/directories to exclude from analysis.",
    )

    @model_validator(mode="after")
    def _enforce_mvp_assist_level(self) -> InstinctConfig:
        """Reject any assist_level except OBSERVE (R4 hook).

        Must run before ``_enforce_corporate_guardrails`` so R4 reserved values
        are gated before we check corporate-specific rules. Pydantic v2 runs
        @model_validator(mode="after") in definition order — do not reorder.
        """
        if self.assist_level is not AssistLevel.OBSERVE:
            raise ValueError(
                f"assist_level must be 'observe' in MVP (got {self.assist_level.value!r}); "
                "other levels are reserved for Release 4."
            )
        return self

    @model_validator(mode="after")
    def _enforce_corporate_guardrails(self) -> InstinctConfig:
        """Apply D5 / D8 / D10 hard guarantees for ``scope: corporate``.

        Accumulates all violations and raises a single ValueError listing every
        one, so the caller sees the full picture in a single pass rather than
        whack-a-mole'ing one field at a time.
        """
        if self.scope is not Scope.CORPORATE:
            return self
        violations: list[str] = []
        if self.sync_allowed:
            violations.append(
                "sync_allowed must be false when scope is 'corporate' (D10 hard guarantee)"
            )
        if self.remote_apis_allowed:
            violations.append(
                "remote_apis_allowed must be false when scope is 'corporate' (D5 hard guarantee)"
            )
        if self.include_in_cross_project:
            violations.append(
                "include_in_cross_project must be false when scope is 'corporate' (D8 hard guarantee)"
            )
        if self.llm_backend is LlmBackend.ANTHROPIC:
            violations.append(
                "llm_backend='anthropic' is not allowed when scope is 'corporate' "
                "(D5 hard guarantee — outbound API traffic from corporate code)"
            )
        if violations:
            raise ValueError("; ".join(violations))
        return self
