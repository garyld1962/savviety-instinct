"""Load per-language cognitive-complexity rule tables from YAML.

Arch §1.2 and §5.5. Rules live in `src/savviety_instinct/core/cognitive_rules/
<lang>.yaml` and are loaded once per process via importlib.resources +
lru_cache. Data-only — the loader is the sole I/O point; the YAML itself
contains no executable code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources

import yaml

from savviety_instinct.core.types import Language
from savviety_instinct.parse.types import ControlFlowNodeKind


@dataclass(frozen=True, slots=True)
class CognitiveIncrement:
    """One row of the increment table: base increment + whether it deepens nesting."""

    base: int
    increments_nesting: bool


@dataclass(frozen=True, slots=True)
class CognitiveRules:
    language: Language
    increments: Mapping[ControlFlowNodeKind, CognitiveIncrement]


_LANG_TO_FILENAME: dict[Language, str] = {
    Language.PYTHON: "python.yaml",
    # Language.RUST / CSHARP / TYPESCRIPT added by Slices 7–8
}


@cache
def load_cognitive_rules(language: Language) -> CognitiveRules:
    if language not in _LANG_TO_FILENAME:
        raise ValueError(
            f"No cognitive rules YAML for {language.value!r}. "
            f"Supported: {sorted(lang.value for lang in _LANG_TO_FILENAME)}."
        )
    filename = _LANG_TO_FILENAME[language]
    content = (
        resources.files("savviety_instinct.core.cognitive_rules")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )
    raw = yaml.safe_load(content)
    if raw.get("language") != language.value:
        raise ValueError(
            f"YAML declares language={raw.get('language')!r} but loader called with "
            f"{language.value!r}"
        )
    increments: dict[ControlFlowNodeKind, CognitiveIncrement] = {}
    for kind_str, rule in raw["increments"].items():
        try:
            kind = ControlFlowNodeKind(kind_str)
        except ValueError as exc:
            raise ValueError(
                f"Unknown ControlFlowNodeKind {kind_str!r} in {filename}; "
                f"add it to the enum or remove the rule."
            ) from exc
        increments[kind] = CognitiveIncrement(
            base=int(rule["base"]),
            increments_nesting=bool(rule["increments_nesting"]),
        )
    missing = set(ControlFlowNodeKind) - set(increments)
    if missing:
        raise ValueError(f"{filename} is missing rules for {sorted(k.value for k in missing)}")
    return CognitiveRules(language=language, increments=increments)
