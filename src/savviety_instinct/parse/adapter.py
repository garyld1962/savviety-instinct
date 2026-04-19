"""LanguageAdapter Protocol and registry (arch §5.5).

Each language implementation registers itself via a module-level
`PYTHON_ADAPTER`-style singleton imported by `get_adapter`. The registry is
populated at this module's import time, not lazily, so runtime errors surface
early.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from savviety_instinct.core.types import Language
from savviety_instinct.parse.types import ParseResult


@runtime_checkable
class LanguageAdapter(Protocol):
    """Parses source into normalized `ParseResult`.

    Implementations MUST be stateless (or memoized-stateful in a thread-safe
    way) so the dispatcher can hold a single instance per language.
    """

    language: Language

    def parse_source(self, source: bytes, file_path: str) -> ParseResult: ...

    def parse_path(self, path: Path) -> ParseResult: ...


_REGISTRY: dict[Language, LanguageAdapter] = {}


def _register(adapter: LanguageAdapter) -> None:
    _REGISTRY[adapter.language] = adapter


def get_adapter(language: Language) -> LanguageAdapter:
    if language not in _REGISTRY:
        raise ValueError(
            f"No adapter registered for {language.value!r}. "
            "Supported languages in this release: "
            f"{sorted(lang.value for lang in _REGISTRY)}"
        )
    return _REGISTRY[language]


# Import side-effects register adapters. Keep this at the bottom to avoid
# circular imports.
from savviety_instinct.parse.python import PYTHON_ADAPTER  # noqa: E402

_register(PYTHON_ADAPTER)
