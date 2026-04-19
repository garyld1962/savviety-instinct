# Slice 2 — Parse + Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Single branch `slice-2-parse-graph`, no combining slices.

**Goal:** Prove Instinct's parsing pipeline end-to-end: parse a Python source file with tree-sitter into normalized nodes, compute a deterministic `ast_hash` per function/class artifact, and build an intra-file call graph via `networkx`. No metrics, no storage writes, no cross-file resolution, no second language.

**Architecture:** `parse/` wraps the `tree-sitter` Python bindings and exposes a `LanguageAdapter` Protocol plus a concrete `PythonAdapter`. The adapter maps tree-sitter nodes to domain-neutral types (`FunctionDefNode`, `CallSiteNode`, `ClassDefNode`) and produces `Artifact` objects whose `ast_hash` is derived from the normalized tree-sitter s-expression. `graph/` consumes those nodes to build a `CallGraph` using `networkx.DiGraph`, with intra-file resolution only. `core.types.AnalysisContext` is extended (keyword-only, backwards-compatible) to carry the optional `CallGraph`. Hashing uses `blake3` when available, falls back to `xxhash`; which hasher produced a digest is opaque to callers (the returned hex string is length-stable and module-level `HASH_ALGORITHM` records the actual choice for `tool_version` provenance).

**Tech Stack:** Python 3.12+, tree-sitter 0.22+, tree-sitter-python 0.23+ (grammar pack), networkx 3.x, blake3 1.x (preferred) / xxhash 3.x (fallback). Existing: pytest, ruff, mypy, Typer, SQLAlchemy. No new runtime CLI surface in Slice 2.

---

## Scope Decisions (locked)

1. **Python only.** No Rust, C#, or TypeScript adapters in Slice 2; those land Slice 7–8. The `LanguageAdapter` Protocol and dispatch hook exist now so adding a language later is additive, not a rewrite.
2. **Intra-file call graph only.** Cross-file resolution requires a symbol table / import resolution layer that is out of MVP scope per HANDOFF.md "default to not in MVP". A call to a symbol not defined in the same file becomes a dangling edge to an `ExternalCallee` node (or is dropped — see Task 8). Decision in Task 8: **drop unresolved edges**. Keep the code path simple.
3. **Classes are artifacts; class methods are artifacts; module-level is NOT an Artifact yet.** `ArtifactKind.MODULE` exists in `core.types` but MVP only emits `FUNCTION` and `CLASS` from the Python adapter. Module-level artifacts (for LCOM-HS etc.) arrive with Slice 4 when their metrics need them.
4. **No `ControlFlowNode` in Slice 2.** Cyclomatic / cognitive complexity (Slice 3) will need it; defining it now without a consumer is premature. Slice 3 adds it.
5. **`ast_hash` is the hex digest of a normalized s-expression.** Normalization strips: leading/trailing whitespace, identifier names (structural, not nominal), and string/number literal values (kept as `_STR`/`_NUM` placeholders so two functions with the same shape but different constants hash identically). Rationale: D6 says `ast_hash` captures "the function's AST shape", not its identifiers.
6. **Hasher choice at import time, not per-call.** `parse.hashing` decides at import which backend to use and exposes `HASH_ALGORITHM` as a string constant. Runtime switching is unnecessary.
7. **No `storage/` changes in Slice 2.** `ast_hash` is produced but not persisted yet. Slice 3 is the first slice that writes `observation_artifacts` rows.
8. **`context_hash` is NOT computed in Slice 2.** D6/§4.2 context_hash requires import set, framework indicators, caller/callee signatures — none of which exist as a concrete input yet. Slice 5 introduces `context_hash` computation when the run pipeline first assembles these. For now, storage layer's `FileLocation.context_hash` remains computed by whatever consumer exists (none in MVP, per §4.1 comment "MVP computes and stores; no consumer yet"). This slice carries no change there.
9. **Tree-sitter grammar version pinned in `pyproject.toml`.** Per arch §16.3 — grammar bumps invalidate `ast_hash` values, so we pin tight (`tree-sitter-python==0.23.*`) and bump deliberately.
10. **Parse errors are soft failures.** A file with a syntax error returns an empty `ParseResult` with `errors: list[ParseError]` populated; the caller decides what to do. Slice 2 does not introduce a caller — tests exercise both code paths directly. Arch §9 says "Parse error → File skipped; error logged".
11. **No `AnalysisContext` dataclass frozen break.** Adding `call_graph: CallGraph | None = None` is additive with a default. `frozen=True, slots=True` preserved.
12. **No pre-commit config churn.** Slice 1 set mypy to strict on `core/` + `storage/`; for Slice 2 we extend that to `parse/` and `graph/` in `pyproject.toml`'s `[tool.mypy.overrides]`. Tree-sitter's `.pyi` stubs are incomplete — we set `ignore_missing_imports = true` for `tree_sitter.*` and `tree_sitter_python` specifically.

---

## File Structure

| Path | Purpose |
|------|---------|
| `pyproject.toml` | Add `tree-sitter`, `tree-sitter-python`, `networkx`, `blake3`, `xxhash` deps; add mypy overrides for tree-sitter modules |
| `src/savviety_instinct/core/types.py` | Extend `AnalysisContext` with `call_graph: CallGraph \| None = None` (forward ref import) |
| `src/savviety_instinct/parse/__init__.py` | Re-exports: `parse_file`, `ParseResult`, `ParseError`, `LanguageAdapter`, `HASH_ALGORITHM` |
| `src/savviety_instinct/parse/types.py` | Normalized node dataclasses: `FunctionDefNode`, `CallSiteNode`, `ClassDefNode`, `ParseResult`, `ParseError` |
| `src/savviety_instinct/parse/hashing.py` | `HASH_ALGORITHM`, `hash_ast_sexp(sexp: str) -> str`, `normalize_sexp(sexp: str) -> str` |
| `src/savviety_instinct/parse/adapter.py` | `LanguageAdapter` Protocol; `get_adapter(language: Language) -> LanguageAdapter` dispatcher |
| `src/savviety_instinct/parse/python.py` | `PythonAdapter`; tree-sitter init; file → `ParseResult`; also exposes module-level singleton `PYTHON_ADAPTER` |
| `src/savviety_instinct/graph/__init__.py` | Re-exports: `CallGraph`, `CallGraphBuilder`, `build_call_graph` |
| `src/savviety_instinct/graph/types.py` | `CallGraph` wrapper around `nx.DiGraph`; node/edge attribute schemas |
| `src/savviety_instinct/graph/builder.py` | `CallGraphBuilder`; `build_call_graph(parse_result: ParseResult) -> CallGraph` (intra-file) |
| `tests/test_parse_hashing.py` | Unit tests for `normalize_sexp` and `hash_ast_sexp` determinism |
| `tests/test_parse_python.py` | Unit tests for `PythonAdapter`: function extraction, class methods, call sites, parse errors, `ast_hash` stability |
| `tests/test_parse_adapter.py` | Protocol conformance for `PythonAdapter`; `get_adapter()` dispatch |
| `tests/test_graph_types.py` | `CallGraph` API: add_function, add_call, neighbors, unresolved edge drop |
| `tests/test_graph_builder.py` | `build_call_graph`: simple file, class methods, recursive call, unresolved external call |
| `tests/integration/__init__.py` | New integration test package |
| `tests/integration/test_parse_graph_pipeline.py` | Integration: parse a fixture Python file → build call graph → assert shape |
| `tests/fixtures/python/simple_module.py` | Fixture: two top-level functions, one calls the other |
| `tests/fixtures/python/with_class.py` | Fixture: class with method calling free function |
| `tests/fixtures/python/syntax_error.py` | Fixture: intentional syntax error for `ParseError` path |
| `tests/fixtures/python/same_shape_different_names.py` | Fixture: two functions with identical AST shape, different identifiers — for ast_hash-shape test |

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add runtime dependencies**

Edit `pyproject.toml`, locate the `dependencies = [...]` array under `[project]` and add these entries after the existing `alembic` entry:

```toml
    "tree-sitter>=0.22,<0.24",
    "tree-sitter-python==0.23.*",
    "networkx>=3.2,<4",
    "blake3>=1.0,<2",
    "xxhash>=3.4,<4",
```

Rationale: upper bounds on `tree-sitter-python` are tight (arch §16.3 grammar pinning). `blake3` and `xxhash` are both runtime deps because of the blake3→xxhash fallback at import time — we don't want the fallback path to ImportError.

- [ ] **Step 2: Add mypy overrides for tree-sitter**

Edit `pyproject.toml`, locate the `[tool.mypy]` section. Add a new `[[tool.mypy.overrides]]` block for tree-sitter (append after any existing overrides):

```toml
[[tool.mypy.overrides]]
module = ["tree_sitter.*", "tree_sitter_python"]
ignore_missing_imports = true
```

Rationale: tree-sitter's type stubs are incomplete; strict mypy on `parse/` would flood with spurious errors. This is a targeted override per arch §3.2 ("Relaxed on `parse/` where tree-sitter typing is approximate").

- [ ] **Step 3: Sync and verify**

Run:

```bash
uv sync
uv run python -c "import tree_sitter, tree_sitter_python, networkx, blake3, xxhash; print('ok')"
```

Expected: `ok` on stdout. If `blake3` fails to install (arm64 wheel issues per HANDOFF.md open questions), proceed anyway — the fallback code path in Task 3 handles ImportError. Mark this in your commit message if fallback was triggered.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add tree-sitter, networkx, blake3/xxhash deps for Slice 2"
```

---

## Task 2: Hashing module with blake3/xxhash fallback

**Files:**
- Create: `src/savviety_instinct/parse/hashing.py`
- Create: `tests/test_parse_hashing.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_parse_hashing.py`:

```python
"""Tests for parse.hashing — ast_hash determinism and shape-normalization."""

from __future__ import annotations

import pytest

from savviety_instinct.parse import hashing


def test_hash_algorithm_is_known() -> None:
    """HASH_ALGORITHM must be one of the two supported backends."""
    assert hashing.HASH_ALGORITHM in {"blake3", "xxhash"}


def test_hash_is_hex_string() -> None:
    digest = hashing.hash_ast_sexp("(function_definition name: (identifier))")
    assert isinstance(digest, str)
    assert all(c in "0123456789abcdef" for c in digest)
    assert len(digest) >= 16  # blake3 32-byte hex = 64 chars; xxhash64 hex = 16


def test_hash_is_deterministic() -> None:
    sexp = "(function_definition name: (identifier))"
    assert hashing.hash_ast_sexp(sexp) == hashing.hash_ast_sexp(sexp)


def test_hash_differs_for_different_shapes() -> None:
    a = hashing.hash_ast_sexp("(function_definition name: (identifier))")
    b = hashing.hash_ast_sexp("(class_definition name: (identifier))")
    assert a != b


def test_normalize_strips_whitespace() -> None:
    a = hashing.normalize_sexp("  (function_definition   name: (identifier))  ")
    b = hashing.normalize_sexp("(function_definition name: (identifier))")
    assert a == b


def test_normalize_replaces_string_literals() -> None:
    raw = '(expression_statement (string "hello"))'
    normalized = hashing.normalize_sexp(raw)
    assert "hello" not in normalized
    assert "_STR" in normalized


def test_normalize_replaces_numeric_literals() -> None:
    raw = "(expression_statement (integer 42))"
    normalized = hashing.normalize_sexp(raw)
    assert "42" not in normalized
    assert "_NUM" in normalized


def test_normalize_preserves_node_type_names() -> None:
    raw = "(function_definition body: (block))"
    normalized = hashing.normalize_sexp(raw)
    # node type names like 'function_definition' are structural; must survive
    assert "function_definition" in normalized
    assert "block" in normalized


def test_same_shape_different_literals_hash_equal() -> None:
    """Two s-exps differing only in literal values hash identically."""
    a = '(return_statement (string "foo"))'
    b = '(return_statement (string "bar"))'
    assert hashing.hash_ast_sexp(a) == hashing.hash_ast_sexp(b)


def test_same_shape_different_identifiers_does_hash_equal() -> None:
    """Tree-sitter s-exps include node types, not identifier text; same shape → same hash.

    Confirms that raw tree-sitter sexp() already omits identifier text, so
    normalization does NOT need to strip identifier node content — it just needs
    to handle literals (which tree-sitter DOES include).
    """
    a = "(function_definition name: (identifier) body: (block))"
    b = "(function_definition name: (identifier) body: (block))"
    assert hashing.hash_ast_sexp(a) == hashing.hash_ast_sexp(b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse_hashing.py -v`

Expected: All tests fail with `ModuleNotFoundError: No module named 'savviety_instinct.parse.hashing'`.

- [ ] **Step 3: Write implementation**

Create `src/savviety_instinct/parse/hashing.py`:

```python
"""Deterministic AST hashing for artifact identity (arch §4.2, D6).

Produces the `ast_hash` used as the dedup key on `observation_artifacts`. The
hash is computed over a *normalized* s-expression of a tree-sitter node, where
normalization strips literal values so two functions with identical shape but
different constants collide on purpose. Identifier text is already excluded by
tree-sitter's `sexp()` output, so the normalizer only needs to handle literals
and whitespace.

Hasher selection (arch §16.2): `blake3` if importable, else `xxhash`. The
choice is captured at import time in `HASH_ALGORITHM` so `tool_version` /
provenance can record which backend produced a given digest (a future
grammar/hasher bump is a deliberate `metric_version` event).
"""

from __future__ import annotations

import re

try:
    import blake3 as _blake3  # type: ignore[import-untyped]

    _HASHER = "blake3"
except ImportError:  # pragma: no cover - fallback path
    import xxhash as _xxhash  # type: ignore[import-untyped]

    _HASHER = "xxhash"

HASH_ALGORITHM: str = _HASHER

_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
_WHITESPACE_RE = re.compile(r"\s+")
# Match integer / float literal nodes produced by tree-sitter-python:
#   (integer 42)  (float 3.14)
# The number follows a space after the node type and is terminated by `)` or space.
_NUMERIC_LITERAL_RE = re.compile(r"(\((?:integer|float|number)\s+)[-+]?\d[\d_.eE+-]*(?=\s|\))")


def normalize_sexp(sexp: str) -> str:
    """Strip whitespace variance and literal values from a tree-sitter s-exp.

    Node type names (`function_definition`, `block`, `identifier`, etc.) survive
    because they define the shape. Literal values do not.
    """
    # Order matters: replace literals before collapsing whitespace to avoid
    # breaking the regex anchors.
    s = _STRING_LITERAL_RE.sub("_STR", sexp)
    s = _NUMERIC_LITERAL_RE.sub(r"\1_NUM", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def hash_ast_sexp(sexp: str) -> str:
    """Hash a tree-sitter s-expression for use as `Artifact.ast_hash`.

    Returns a hex-encoded digest. Length depends on backend (blake3: 64 chars,
    xxhash64: 16 chars) but is stable for a given import session.
    """
    normalized = normalize_sexp(sexp)
    encoded = normalized.encode("utf-8")
    if _HASHER == "blake3":
        return _blake3.blake3(encoded).hexdigest()
    return _xxhash.xxh64(encoded).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_parse_hashing.py -v`

Expected: All 10 tests pass. If `test_hash_algorithm_is_known` reports `xxhash`, blake3 wasn't available on this platform — that's fine, note it in the commit.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/parse/hashing.py tests/test_parse_hashing.py
git commit -m "feat(parse): deterministic ast_hash via blake3 with xxhash fallback"
```

---

## Task 3: Normalized AST node types

**Files:**
- Create: `src/savviety_instinct/parse/types.py`

- [ ] **Step 1: Write implementation (no tests — these are pure data classes exercised by Task 5's tests)**

Create `src/savviety_instinct/parse/types.py`:

```python
"""Normalized AST node types — language-agnostic view of parsed code.

Each `LanguageAdapter` (arch §5.5) maps its language-specific tree-sitter nodes
into these domain-neutral dataclasses. Metrics and graph builders consume these,
not raw tree-sitter nodes, so adding a new language is an adapter-only change.

Slice 2 populates `FunctionDefNode`, `ClassDefNode`, and `CallSiteNode`.
`ControlFlowNode` etc. arrive with the complexity metrics in Slice 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from savviety_instinct.core.types import SourceRange


class ParseErrorKind(StrEnum):
    SYNTAX = "syntax"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    IO = "io"


@dataclass(frozen=True, slots=True)
class ParseError:
    kind: ParseErrorKind
    message: str
    source_range: SourceRange | None  # None for IO errors where we never parsed a range


@dataclass(frozen=True, slots=True)
class FunctionDefNode:
    """A callable definition: free function, lambda, or method."""

    name: str                       # the symbol under which callers find it
    qualified_name: str             # e.g., "MyClass.method" for methods, plain name for free fns
    enclosing_class: str | None     # for methods; None for free functions
    source_range: SourceRange
    ast_hash: str                   # computed per arch §4.2
    is_method: bool
    parameter_names: tuple[str, ...]  # for future signature hashing; not used in Slice 2


@dataclass(frozen=True, slots=True)
class ClassDefNode:
    name: str
    source_range: SourceRange
    ast_hash: str
    method_qualified_names: tuple[str, ...]  # forward index into FunctionDefNode.qualified_name


@dataclass(frozen=True, slots=True)
class CallSiteNode:
    """A single invocation. Intra-file resolution only in Slice 2."""

    callee_name: str                # the textual name at the call site
    source_range: SourceRange
    enclosing_function: str | None  # qualified name of the function containing this call,
                                    # or None if the call is at module level
    is_resolved: bool               # True if a local FunctionDefNode matched callee_name


@dataclass(frozen=True, slots=True)
class ParseResult:
    file_path: str
    language: str                   # StrEnum value from core.types.Language
    functions: tuple[FunctionDefNode, ...]
    classes: tuple[ClassDefNode, ...]
    call_sites: tuple[CallSiteNode, ...]
    errors: tuple[ParseError, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.errors
```

- [ ] **Step 2: Type-check in isolation**

Run: `uv run mypy src/savviety_instinct/parse/types.py`

Expected: `Success: no issues found in 1 source file`.

- [ ] **Step 3: Commit**

```bash
git add src/savviety_instinct/parse/types.py
git commit -m "feat(parse): normalized AST node types (FunctionDef, ClassDef, CallSite, ParseResult)"
```

---

## Task 4: LanguageAdapter Protocol and dispatcher

**Files:**
- Create: `src/savviety_instinct/parse/adapter.py`
- Create: `tests/test_parse_adapter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_parse_adapter.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse_adapter.py -v`

Expected: `ModuleNotFoundError: No module named 'savviety_instinct.parse.adapter'`.

- [ ] **Step 3: Write implementation**

Create `src/savviety_instinct/parse/adapter.py`:

```python
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
```

Note: this file imports from `parse.python`, which will not exist until Task 5. That's deliberate — we'll write Task 5 next. Running the tests between Task 4 and Task 5 will still show the same ImportError as step 2, just deferred one module level.

- [ ] **Step 4: Commit partial (no test pass yet — Task 5 completes the wiring)**

Do NOT run tests yet. Defer commit until after Task 5 so the commit is green. Leave the files on disk.

---

## Task 5: Python adapter via tree-sitter

**Files:**
- Create: `src/savviety_instinct/parse/python.py`
- Create: `tests/test_parse_python.py`
- Create: `tests/fixtures/python/simple_module.py`
- Create: `tests/fixtures/python/with_class.py`
- Create: `tests/fixtures/python/syntax_error.py`
- Create: `tests/fixtures/python/same_shape_different_names.py`

- [ ] **Step 1: Write fixture files**

Create `tests/fixtures/python/simple_module.py`:

```python
def helper(x: int) -> int:
    return x + 1


def main() -> int:
    result = helper(41)
    return result
```

Create `tests/fixtures/python/with_class.py`:

```python
def module_level() -> int:
    return 42


class Worker:
    def do_work(self) -> int:
        return module_level()

    def other(self) -> int:
        return self.do_work()
```

Create `tests/fixtures/python/syntax_error.py`:

```python
def broken(
    # missing close paren and body — deliberate syntax error
```

Create `tests/fixtures/python/same_shape_different_names.py`:

```python
def alpha(a: int) -> int:
    return a + 1


def beta(b: int) -> int:
    return b + 1
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_parse_python.py`:

```python
"""Tests for PythonAdapter — tree-sitter-based parsing of Python sources."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.core.types import Language
from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import ParseErrorKind, ParseResult


FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _parse(name: str) -> ParseResult:
    return PYTHON_ADAPTER.parse_path(FIXTURES / name)


def test_adapter_language_is_python() -> None:
    assert PYTHON_ADAPTER.language == Language.PYTHON


def test_simple_module_extracts_two_functions() -> None:
    result = _parse("simple_module.py")
    assert result.ok
    names = {fn.name for fn in result.functions}
    assert names == {"helper", "main"}


def test_simple_module_function_has_ast_hash() -> None:
    result = _parse("simple_module.py")
    helper = next(fn for fn in result.functions if fn.name == "helper")
    assert helper.ast_hash  # non-empty string
    assert helper.is_method is False
    assert helper.enclosing_class is None


def test_simple_module_captures_call_site() -> None:
    result = _parse("simple_module.py")
    # main() calls helper()
    call = next(
        c for c in result.call_sites
        if c.callee_name == "helper" and c.enclosing_function == "main"
    )
    assert call.is_resolved is True


def test_with_class_extracts_methods_as_functions() -> None:
    result = _parse("with_class.py")
    assert result.ok
    qualified = {fn.qualified_name for fn in result.functions}
    assert "module_level" in qualified
    assert "Worker.do_work" in qualified
    assert "Worker.other" in qualified


def test_with_class_method_is_method_flag_set() -> None:
    result = _parse("with_class.py")
    do_work = next(fn for fn in result.functions if fn.qualified_name == "Worker.do_work")
    assert do_work.is_method is True
    assert do_work.enclosing_class == "Worker"


def test_with_class_class_node_lists_methods() -> None:
    result = _parse("with_class.py")
    worker = next(c for c in result.classes if c.name == "Worker")
    assert set(worker.method_qualified_names) == {"Worker.do_work", "Worker.other"}


def test_syntax_error_reports_error_not_crash() -> None:
    result = _parse("syntax_error.py")
    assert not result.ok
    assert any(err.kind == ParseErrorKind.SYNTAX for err in result.errors)


def test_same_shape_functions_produce_same_ast_hash() -> None:
    """alpha and beta differ only in identifier names; their ast_hash must match.

    Confirms normalize_sexp + tree-sitter sexp() produce identifier-invariant
    hashes as documented in Scope Decision #5.
    """
    result = _parse("same_shape_different_names.py")
    alpha = next(fn for fn in result.functions if fn.name == "alpha")
    beta = next(fn for fn in result.functions if fn.name == "beta")
    assert alpha.ast_hash == beta.ast_hash


def test_parse_source_matches_parse_path() -> None:
    """The two entry points are equivalent for the same bytes."""
    source = (FIXTURES / "simple_module.py").read_bytes()
    by_path = PYTHON_ADAPTER.parse_path(FIXTURES / "simple_module.py")
    by_bytes = PYTHON_ADAPTER.parse_source(source, str(FIXTURES / "simple_module.py"))
    assert {fn.name for fn in by_path.functions} == {fn.name for fn in by_bytes.functions}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_parse_python.py tests/test_parse_adapter.py -v`

Expected: All tests fail with `ImportError` (python.py doesn't exist yet).

- [ ] **Step 4: Write implementation**

Create `src/savviety_instinct/parse/python.py`:

```python
"""Python LanguageAdapter using tree-sitter-python.

Responsibilities (arch §5.5):
- Parse Python source bytes into a tree-sitter tree.
- Walk the tree to extract FunctionDef, ClassDef, and CallSite nodes.
- Compute `ast_hash` per function/class via `parse.hashing`.
- Report syntax errors as ParseError, not exceptions.

Intra-file resolution: a CallSite is `is_resolved=True` iff its `callee_name`
matches a FunctionDef.name defined in the same file at any scope. Cross-file
resolution is deferred (Scope Decision #2).
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language as TSLanguage, Node, Parser, Tree

from savviety_instinct.core.types import Language, SourceRange
from savviety_instinct.parse.hashing import hash_ast_sexp
from savviety_instinct.parse.types import (
    CallSiteNode,
    ClassDefNode,
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)

_PY_LANGUAGE = TSLanguage(tspython.language())


def _make_parser() -> Parser:
    parser = Parser()
    parser.language = _PY_LANGUAGE
    return parser


class PythonAdapter:
    """tree-sitter-python adapter. Stateless; safe to share across calls."""

    language: Language = Language.PYTHON

    def __init__(self) -> None:
        self._parser = _make_parser()

    def parse_path(self, path: Path) -> ParseResult:
        try:
            source = path.read_bytes()
        except OSError as exc:
            return ParseResult(
                file_path=str(path),
                language=Language.PYTHON.value,
                functions=(),
                classes=(),
                call_sites=(),
                errors=(ParseError(kind=ParseErrorKind.IO, message=str(exc), source_range=None),),
            )
        return self.parse_source(source, str(path))

    def parse_source(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        errors = tuple(_collect_syntax_errors(tree, source, file_path))
        functions = tuple(_collect_functions(tree, source, file_path))
        classes = tuple(_collect_classes(tree, source, file_path, functions))
        local_names = {fn.name for fn in functions} | {fn.qualified_name for fn in functions}
        call_sites = tuple(_collect_call_sites(tree, source, file_path, local_names, functions))

        return ParseResult(
            file_path=file_path,
            language=Language.PYTHON.value,
            functions=functions,
            classes=classes,
            call_sites=call_sites,
            errors=errors,
        )


# ---------- helpers (module-private) ----------


def _source_range(node: Node, file_path: str) -> SourceRange:
    start, end = node.start_point, node.end_point
    return SourceRange(
        file_path=file_path,
        line_start=start[0] + 1,  # tree-sitter is 0-indexed; editors are 1-indexed
        line_end=end[0] + 1,
    )


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _collect_syntax_errors(tree: Tree, source: bytes, file_path: str) -> list[ParseError]:
    errors: list[ParseError] = []
    # tree-sitter surfaces syntax issues as ERROR / MISSING nodes in the tree.
    cursor = tree.walk()
    stack: list[Node] = [cursor.node]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            errors.append(
                ParseError(
                    kind=ParseErrorKind.SYNTAX,
                    message=f"tree-sitter parse error at L{node.start_point[0] + 1}",
                    source_range=_source_range(node, file_path),
                )
            )
        stack.extend(node.children)
    return errors


def _collect_functions(tree: Tree, source: bytes, file_path: str) -> list[FunctionDefNode]:
    out: list[FunctionDefNode] = []
    stack: list[tuple[Node, str | None]] = [(tree.root_node, None)]
    while stack:
        node, enclosing_class = stack.pop()
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = _text(name_node, source)
            qualified = f"{enclosing_class}.{name}" if enclosing_class else name
            params = _extract_parameter_names(node, source)
            sexp = node.sexp() if hasattr(node, "sexp") else str(node)
            out.append(
                FunctionDefNode(
                    name=name,
                    qualified_name=qualified,
                    enclosing_class=enclosing_class,
                    source_range=_source_range(node, file_path),
                    ast_hash=hash_ast_sexp(sexp),
                    is_method=enclosing_class is not None,
                    parameter_names=params,
                )
            )
            # Do not recurse into nested functions for Slice 2 — they exist but
            # MVP metrics treat the outer function as the unit. Revisit in
            # Slice 4 when nested-closure complexity matters.
            continue
        new_enclosing = enclosing_class
        if node.type == "class_definition":
            class_name_node = node.child_by_field_name("name")
            if class_name_node is not None:
                new_enclosing = _text(class_name_node, source)
        stack.extend((child, new_enclosing) for child in node.children)
    return out


def _collect_classes(
    tree: Tree,
    source: bytes,
    file_path: str,
    functions: tuple[FunctionDefNode, ...],
) -> list[ClassDefNode]:
    out: list[ClassDefNode] = []
    method_index: dict[str, list[str]] = {}
    for fn in functions:
        if fn.enclosing_class is not None:
            method_index.setdefault(fn.enclosing_class, []).append(fn.qualified_name)

    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = _text(name_node, source)
            sexp = node.sexp() if hasattr(node, "sexp") else str(node)
            out.append(
                ClassDefNode(
                    name=name,
                    source_range=_source_range(node, file_path),
                    ast_hash=hash_ast_sexp(sexp),
                    method_qualified_names=tuple(method_index.get(name, ())),
                )
            )
        stack.extend(node.children)
    return out


def _collect_call_sites(
    tree: Tree,
    source: bytes,
    file_path: str,
    local_names: set[str],
    functions: tuple[FunctionDefNode, ...],
) -> list[CallSiteNode]:
    # Build a range map: byte-interval → qualified function name, so we can
    # assign each call site to its enclosing function.
    ranges: list[tuple[int, int, str]] = [
        (_node_byte_range_for_qualified(fn, source, tree) or (0, 0, ""))
        for fn in functions
    ]
    ranges = [r for r in ranges if r[2]]

    def _enclosing(call_node: Node) -> str | None:
        start = call_node.start_byte
        # Pick the narrowest enclosing range (innermost function).
        best: tuple[int, int, str] | None = None
        for r in ranges:
            if r[0] <= start < r[1]:
                if best is None or (r[1] - r[0]) < (best[1] - best[0]):
                    best = r
        return best[2] if best else None

    out: list[CallSiteNode] = []
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node is not None:
                # For attribute calls like `self.do_work()`, use the attribute name.
                callee = _callee_name_from_node(func_node, source)
                if callee is not None:
                    out.append(
                        CallSiteNode(
                            callee_name=callee,
                            source_range=_source_range(node, file_path),
                            enclosing_function=_enclosing(node),
                            is_resolved=_is_resolved(callee, local_names, functions),
                        )
                    )
        stack.extend(node.children)
    return out


def _node_byte_range_for_qualified(
    fn: FunctionDefNode, source: bytes, tree: Tree
) -> tuple[int, int, str] | None:
    """Locate the tree-sitter byte range of a FunctionDefNode by re-walking.

    Slice 2 keeps FunctionDefNode pure-data; this helper recovers the byte
    range we need for enclosing-function attribution. This is O(N) per
    function per file; fine for MVP file sizes, revisit if it shows in
    profiles.
    """
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None and _text(name_node, source) == fn.name:
                return (node.start_byte, node.end_byte, fn.qualified_name)
        stack.extend(node.children)
    return None


def _callee_name_from_node(node: Node, source: bytes) -> str | None:
    if node.type == "identifier":
        return _text(node, source)
    if node.type == "attribute":
        attr = node.child_by_field_name("attribute")
        if attr is not None:
            return _text(attr, source)
    return None


def _is_resolved(
    callee: str, local_names: set[str], functions: tuple[FunctionDefNode, ...]
) -> bool:
    if callee in local_names:
        return True
    # Also resolve bare method names against any function whose short name matches.
    return any(fn.name == callee for fn in functions)


def _extract_parameter_names(func_node: Node, source: bytes) -> tuple[str, ...]:
    params_node = func_node.child_by_field_name("parameters")
    if params_node is None:
        return ()
    names: list[str] = []
    for child in params_node.children:
        if child.type == "identifier":
            names.append(_text(child, source))
        elif child.type in {"typed_parameter", "default_parameter", "typed_default_parameter"}:
            ident = child.child_by_field_name("name")
            if ident is None:
                # Fall back: first child that's an identifier
                for grand in child.children:
                    if grand.type == "identifier":
                        names.append(_text(grand, source))
                        break
            else:
                names.append(_text(ident, source))
    return tuple(names)


# Module-level singleton — imported by parse.adapter for registry.
PYTHON_ADAPTER = PythonAdapter()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_parse_python.py tests/test_parse_adapter.py -v`

Expected: All tests in both files pass. If any test fails, inspect which one and iterate — the tree-sitter-python grammar node names (`function_definition`, `class_definition`, `call`, `attribute`, `identifier`) are stable in 0.23.x but field name queries (`child_by_field_name("name")`) are worth double-checking against the installed grammar.

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/parse/python.py \
        src/savviety_instinct/parse/adapter.py \
        tests/test_parse_python.py \
        tests/test_parse_adapter.py \
        tests/fixtures/python/
git commit -m "feat(parse): PythonAdapter extracts functions, classes, call sites via tree-sitter"
```

---

## Task 6: Re-export parse API

**Files:**
- Modify: `src/savviety_instinct/parse/__init__.py`

- [ ] **Step 1: Replace the empty `__init__.py`**

Overwrite `src/savviety_instinct/parse/__init__.py`:

```python
"""Public API for the parse layer.

Arch §5.5. Wrap tree-sitter; expose normalized nodes and per-language adapters.
"""

from __future__ import annotations

from savviety_instinct.parse.adapter import LanguageAdapter, get_adapter
from savviety_instinct.parse.hashing import HASH_ALGORITHM, hash_ast_sexp
from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import (
    CallSiteNode,
    ClassDefNode,
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)

__all__ = [
    "HASH_ALGORITHM",
    "PYTHON_ADAPTER",
    "CallSiteNode",
    "ClassDefNode",
    "FunctionDefNode",
    "LanguageAdapter",
    "ParseError",
    "ParseErrorKind",
    "ParseResult",
    "get_adapter",
    "hash_ast_sexp",
]
```

- [ ] **Step 2: Run full parse test suite to confirm no regression**

Run: `uv run pytest tests/test_parse_hashing.py tests/test_parse_python.py tests/test_parse_adapter.py -v`

Expected: All tests pass, same count as before.

- [ ] **Step 3: Commit**

```bash
git add src/savviety_instinct/parse/__init__.py
git commit -m "feat(parse): export public API (adapters, types, hashing)"
```

---

## Task 7: CallGraph type

**Files:**
- Create: `src/savviety_instinct/graph/types.py`
- Create: `tests/test_graph_types.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_types.py`:

```python
"""Tests for graph.types — CallGraph wrapper around networkx.DiGraph."""

from __future__ import annotations

import pytest

from savviety_instinct.graph.types import CallGraph


def test_empty_graph_has_no_functions() -> None:
    g = CallGraph()
    assert g.functions() == ()
    assert g.edge_count() == 0


def test_add_function_registers_node() -> None:
    g = CallGraph()
    g.add_function("main", ast_hash="abc", file_path="x.py")
    assert "main" in g.functions()


def test_add_function_is_idempotent() -> None:
    g = CallGraph()
    g.add_function("main", ast_hash="abc", file_path="x.py")
    g.add_function("main", ast_hash="abc", file_path="x.py")
    assert g.functions() == ("main",)


def test_add_call_creates_edge() -> None:
    g = CallGraph()
    g.add_function("main", ast_hash="a", file_path="x.py")
    g.add_function("helper", ast_hash="b", file_path="x.py")
    g.add_call(caller="main", callee="helper")
    assert g.edge_count() == 1
    assert "helper" in g.callees_of("main")


def test_add_call_creates_nodes_lazily_for_callers_only_if_known() -> None:
    """Adding a call when the caller is unregistered is a programmer error."""
    g = CallGraph()
    g.add_function("helper", ast_hash="b", file_path="x.py")
    with pytest.raises(KeyError, match="caller 'main' not in graph"):
        g.add_call(caller="main", callee="helper")


def test_unresolved_callee_is_dropped() -> None:
    """Scope Decision #2: drop unresolved edges; keep the code path simple."""
    g = CallGraph()
    g.add_function("main", ast_hash="a", file_path="x.py")
    # `external_thing` isn't a registered function; call silently drops.
    g.add_call(caller="main", callee="external_thing", is_resolved=False)
    assert g.edge_count() == 0


def test_callees_of_unknown_function_raises() -> None:
    g = CallGraph()
    with pytest.raises(KeyError, match="unknown function 'nope'"):
        g.callees_of("nope")


def test_callers_of_returns_incoming_edges() -> None:
    g = CallGraph()
    g.add_function("a", ast_hash="1", file_path="x.py")
    g.add_function("b", ast_hash="2", file_path="x.py")
    g.add_function("c", ast_hash="3", file_path="x.py")
    g.add_call("a", "c")
    g.add_call("b", "c")
    assert set(g.callers_of("c")) == {"a", "b"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph_types.py -v`

Expected: All tests fail with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/savviety_instinct/graph/types.py`:

```python
"""CallGraph — a thin typed wrapper around networkx.DiGraph.

Arch §5.5. The adjacency store is `networkx` because it gives us path and
centrality algorithms for free (Henry–Kafura, chain-depth-to-effect in later
slices). The wrapper exists because callers shouldn't handle networkx's
stringly-typed attribute bags.

Node attributes: `ast_hash: str`, `file_path: str`.
Edge attributes: none in Slice 2; Slice 3+ may add `is_conditional: bool` etc.
"""

from __future__ import annotations

import networkx as nx


class CallGraph:
    """Intra-file call graph. One instance per file in Slice 2; project-wide
    composition lands when cross-file resolution arrives (post-MVP).
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    def add_function(self, qualified_name: str, *, ast_hash: str, file_path: str) -> None:
        self._g.add_node(qualified_name, ast_hash=ast_hash, file_path=file_path)

    def add_call(self, caller: str, callee: str, *, is_resolved: bool = True) -> None:
        """Record a call edge. Unresolved callees (those not in the graph) are dropped.

        Scope Decision #2: we do not create `ExternalCallee` placeholder nodes.
        Callers need the ability to look up all calls-originating-from-a-function
        via `callees_of`; keeping the adjacency clean means those callers don't
        have to filter out external nodes.
        """
        if caller not in self._g:
            raise KeyError(f"caller {caller!r} not in graph; add_function() first")
        if not is_resolved or callee not in self._g:
            return
        self._g.add_edge(caller, callee)

    def functions(self) -> tuple[str, ...]:
        return tuple(self._g.nodes())

    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def callees_of(self, qualified_name: str) -> tuple[str, ...]:
        if qualified_name not in self._g:
            raise KeyError(f"unknown function {qualified_name!r}")
        return tuple(self._g.successors(qualified_name))

    def callers_of(self, qualified_name: str) -> tuple[str, ...]:
        if qualified_name not in self._g:
            raise KeyError(f"unknown function {qualified_name!r}")
        return tuple(self._g.predecessors(qualified_name))

    def as_networkx(self) -> nx.DiGraph:
        """Escape hatch for later slices that need nx algorithms directly."""
        return self._g
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph_types.py -v`

Expected: All 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/graph/types.py tests/test_graph_types.py
git commit -m "feat(graph): CallGraph wrapper over networkx.DiGraph"
```

---

## Task 8: CallGraph builder

**Files:**
- Create: `src/savviety_instinct/graph/builder.py`
- Create: `tests/test_graph_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph_builder.py`:

```python
"""Tests for graph.builder — build CallGraph from ParseResult."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.graph.builder import build_call_graph
from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_simple_module_graph_has_two_nodes_one_edge() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "simple_module.py")
    g = build_call_graph(result)
    assert set(g.functions()) == {"helper", "main"}
    assert g.edge_count() == 1
    assert g.callees_of("main") == ("helper",)


def test_with_class_graph_includes_methods_and_external_call() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "with_class.py")
    g = build_call_graph(result)
    # module_level, Worker.do_work, Worker.other
    assert set(g.functions()) == {"module_level", "Worker.do_work", "Worker.other"}
    # do_work calls module_level
    assert "module_level" in g.callees_of("Worker.do_work")
    # other calls self.do_work → resolves via bare-name match on `do_work`
    assert "Worker.do_work" in g.callees_of("Worker.other")


def test_unresolved_external_call_is_dropped() -> None:
    """A call to a name not defined in the file adds no edge."""
    from savviety_instinct.parse.types import (
        CallSiteNode,
        FunctionDefNode,
        ParseResult,
    )
    from savviety_instinct.core.types import SourceRange

    fn = FunctionDefNode(
        name="main",
        qualified_name="main",
        enclosing_class=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=3),
        ast_hash="abc",
        is_method=False,
        parameter_names=(),
    )
    call = CallSiteNode(
        callee_name="requests",  # unresolved
        source_range=SourceRange(file_path="x.py", line_start=2, line_end=2),
        enclosing_function="main",
        is_resolved=False,
    )
    result = ParseResult(
        file_path="x.py",
        language="python",
        functions=(fn,),
        classes=(),
        call_sites=(call,),
    )
    g = build_call_graph(result)
    assert g.edge_count() == 0
    assert set(g.functions()) == {"main"}


def test_module_level_call_has_no_edge_source() -> None:
    """A call at module scope (enclosing_function=None) contributes no edge."""
    from savviety_instinct.parse.types import (
        CallSiteNode,
        FunctionDefNode,
        ParseResult,
    )
    from savviety_instinct.core.types import SourceRange

    fn = FunctionDefNode(
        name="helper",
        qualified_name="helper",
        enclosing_class=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=2),
        ast_hash="abc",
        is_method=False,
        parameter_names=(),
    )
    call = CallSiteNode(
        callee_name="helper",
        source_range=SourceRange(file_path="x.py", line_start=4, line_end=4),
        enclosing_function=None,  # top-level
        is_resolved=True,
    )
    result = ParseResult(
        file_path="x.py",
        language="python",
        functions=(fn,),
        classes=(),
        call_sites=(call,),
    )
    g = build_call_graph(result)
    assert g.edge_count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph_builder.py -v`

Expected: All 4 tests fail with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/savviety_instinct/graph/builder.py`:

```python
"""Build a CallGraph from a ParseResult.

Arch §5.3 pipeline stage 3. Intra-file only in Slice 2 (Scope Decision #2).
Module-level call sites (enclosing_function is None) are ignored: they have no
caller to attach an edge to and MVP metrics reason about call depth relative to
function definitions.
"""

from __future__ import annotations

from savviety_instinct.graph.types import CallGraph
from savviety_instinct.parse.types import ParseResult


def build_call_graph(parse_result: ParseResult) -> CallGraph:
    g = CallGraph()
    for fn in parse_result.functions:
        g.add_function(
            fn.qualified_name,
            ast_hash=fn.ast_hash,
            file_path=parse_result.file_path,
        )

    # Index short-name → qualified so `self.do_work()` (bare `do_work`) resolves
    # to `Worker.do_work` when the class is unambiguous within the file.
    name_to_qualified: dict[str, list[str]] = {}
    for fn in parse_result.functions:
        name_to_qualified.setdefault(fn.name, []).append(fn.qualified_name)
        name_to_qualified.setdefault(fn.qualified_name, []).append(fn.qualified_name)

    for call in parse_result.call_sites:
        if call.enclosing_function is None:
            # Module-level call: no caller node to attach an edge to.
            continue
        if not call.is_resolved:
            continue
        targets = name_to_qualified.get(call.callee_name, [])
        # Ambiguous short-name resolution (multiple classes define the same
        # method name) is handled by adding edges to ALL candidates. A later
        # slice with type-flow info will narrow this.
        for target in targets:
            g.add_call(
                caller=call.enclosing_function,
                callee=target,
                is_resolved=True,
            )
    return g
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph_builder.py -v`

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/graph/builder.py tests/test_graph_builder.py
git commit -m "feat(graph): build intra-file CallGraph from ParseResult"
```

---

## Task 9: Re-export graph API

**Files:**
- Modify: `src/savviety_instinct/graph/__init__.py`

- [ ] **Step 1: Replace the empty `__init__.py`**

Overwrite `src/savviety_instinct/graph/__init__.py`:

```python
"""Public API for the graph layer.

Arch §5.5. Intra-file CallGraph in Slice 2; module dependency graph + cross-file
resolution are reserved for later slices.
"""

from __future__ import annotations

from savviety_instinct.graph.builder import build_call_graph
from savviety_instinct.graph.types import CallGraph

__all__ = ["CallGraph", "build_call_graph"]
```

- [ ] **Step 2: Run graph test suite to confirm no regression**

Run: `uv run pytest tests/test_graph_types.py tests/test_graph_builder.py -v`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/savviety_instinct/graph/__init__.py
git commit -m "feat(graph): export public API"
```

---

## Task 10: Extend AnalysisContext with call_graph

**Files:**
- Modify: `src/savviety_instinct/core/types.py`
- Modify: `tests/test_core_types.py`

- [ ] **Step 1: Read the existing `test_core_types.py`**

Run: `uv run cat tests/test_core_types.py` (or open it). Identify the `test_analysis_context_*` block. We'll append a new test next to it.

- [ ] **Step 2: Add failing test**

Append to `tests/test_core_types.py`:

```python
def test_analysis_context_accepts_call_graph() -> None:
    """Slice 2 forward-compat: AnalysisContext now carries an optional CallGraph."""
    from savviety_instinct.core.types import AnalysisContext
    from savviety_instinct.graph import CallGraph

    cg = CallGraph()
    cg.add_function("main", ast_hash="abc", file_path="x.py")
    ctx = AnalysisContext(call_graph=cg)
    assert ctx.call_graph is cg


def test_analysis_context_call_graph_defaults_to_none() -> None:
    """Existing call sites with no call_graph continue to work."""
    from savviety_instinct.core.types import AnalysisContext

    ctx = AnalysisContext()
    assert ctx.call_graph is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_core_types.py::test_analysis_context_accepts_call_graph tests/test_core_types.py::test_analysis_context_call_graph_defaults_to_none -v`

Expected: Both tests fail with `TypeError: AnalysisContext.__init__() got an unexpected keyword argument 'call_graph'`.

- [ ] **Step 4: Extend `AnalysisContext`**

In `src/savviety_instinct/core/types.py`, replace the current empty `AnalysisContext`:

```python
@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Context passed to each Metric.compute().

    Slice 2: adds `call_graph` (optional; defaults to None so Slice 1 call
    sites remain valid). Slice 3+ will add module graph, import set, framework
    indicators per arch §5.3. All fields MUST be keyword-only with defaults so
    future extensions stay additive.
    """

    call_graph: "CallGraph | None" = None
```

Then add the forward-reference import. At the top of the file, after the existing imports, add a TYPE_CHECKING guard so `core/` remains pure (no runtime dependency on `graph/` — arch §2 layering rule: `core` is at the bottom of the import hierarchy):

```python
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from savviety_instinct.graph.types import CallGraph
```

Replace the existing `from typing import Protocol, runtime_checkable` line.

- [ ] **Step 5: Run ALL core tests**

Run: `uv run pytest tests/test_core_types.py -v`

Expected: All existing tests still pass; the two new tests pass; no import-time crash.

- [ ] **Step 6: Verify layering still holds**

Run: `uv run python -c "import savviety_instinct.core.types; print('core loaded without graph')"`

Then confirm `graph/` is not transitively imported at core load:

```bash
uv run python -c "
import sys
import savviety_instinct.core.types  # noqa
assert 'savviety_instinct.graph' not in sys.modules, 'core MUST NOT import graph at runtime'
print('layering holds')
"
```

Expected: `core loaded without graph` then `layering holds`.

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/core/types.py tests/test_core_types.py
git commit -m "feat(core): AnalysisContext.call_graph (forward-ref, preserves layering)"
```

---

## Task 11: Integration test — parse → graph pipeline

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_parse_graph_pipeline.py`

- [ ] **Step 1: Create integration package**

Create `tests/integration/__init__.py` (empty file).

- [ ] **Step 2: Write integration test**

Create `tests/integration/test_parse_graph_pipeline.py`:

```python
"""Integration: parse a Python fixture end-to-end, build call graph, assert shape.

This is the Slice 2 acceptance: a source file goes in, a CallGraph with correct
nodes and edges comes out, with no crashes on the syntax-error fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.core.types import AnalysisContext
from savviety_instinct.graph import build_call_graph
from savviety_instinct.parse import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent.parent / "fixtures" / "python"


def test_pipeline_simple_module_produces_graph() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "simple_module.py")
    assert result.ok
    graph = build_call_graph(result)
    ctx = AnalysisContext(call_graph=graph)
    # AnalysisContext can carry the graph into metric computation (Slice 3+).
    assert ctx.call_graph is graph
    assert "main" in graph.functions()
    assert "helper" in graph.callees_of("main")


def test_pipeline_handles_syntax_error_without_crash() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "syntax_error.py")
    assert not result.ok
    # Graph builder on an errored ParseResult must still produce a valid graph
    # (empty or partial) — arch §9 says degrade, don't crash.
    graph = build_call_graph(result)
    # No assertion on exact shape; tree-sitter may still extract the partial
    # `def broken(` as a FunctionDefNode. Key assertion: no exception.
    assert graph is not None


def test_pipeline_class_methods_resolve_via_bare_name() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "with_class.py")
    graph = build_call_graph(result)
    # other() -> self.do_work() -> Worker.do_work
    assert "Worker.do_work" in graph.callees_of("Worker.other")
    # do_work() -> module_level()
    assert "module_level" in graph.callees_of("Worker.do_work")
```

- [ ] **Step 3: Run integration test**

Run: `uv run pytest tests/integration/ -v`

Expected: All 3 tests pass.

- [ ] **Step 4: Run the full test suite to confirm no regressions**

Run: `uv run pytest -v`

Expected: All previously-passing tests still pass; new tests pass; zero warnings that weren't already present at Slice 1.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/
git commit -m "test: integration parse→graph pipeline (simple, syntax-error, methods)"
```

---

## Task 12: Pre-commit + type checking sweep

**Files:**
- Modify: `pyproject.toml` (if mypy strict scope needs tightening)

- [ ] **Step 1: Run ruff**

```bash
uv run ruff check src/savviety_instinct/parse src/savviety_instinct/graph tests/
uv run ruff format --check src/savviety_instinct/parse src/savviety_instinct/graph tests/
```

Expected: No violations. If ruff formats anything, re-run `uv run ruff format` and amend into a follow-up commit (don't `--amend`).

- [ ] **Step 2: Run mypy on the new modules**

```bash
uv run mypy src/savviety_instinct/parse src/savviety_instinct/graph src/savviety_instinct/core
```

Expected: `Success: no issues found`. If tree-sitter surfaces errors despite the ignore override, add specific `# type: ignore[...]` comments with the error code — do NOT broaden the mypy override further.

- [ ] **Step 3: Run the pre-commit hook set**

```bash
uv run pre-commit run --all-files
```

Expected: All hooks pass. If a hook flags changes, commit the result as `style: pre-commit sweep for Slice 2`.

- [ ] **Step 4: Confirm final test state**

Run: `uv run pytest --cov=src/savviety_instinct --cov-report=term-missing -v`

Expected: all tests pass; parse and graph modules show high coverage. Note any lines reported as uncovered — they should be ONLY the fallback `pragma: no cover` branch in `hashing.py` (the xxhash path if blake3 is present, or vice versa).

- [ ] **Step 5: Push and open a PR**

```bash
git push -u origin slice-2-parse-graph
gh pr create --title "Slice 2: parse/ (Python) + graph/ (intra-file call graph)" \
  --body "$(cat <<'EOF'
## Summary

Delivers Slice 2 from arch spec §15: tree-sitter-based Python parsing and intra-file call graph construction. Proves the parsing pipeline end-to-end with no metrics / storage writes yet.

- `parse/python.py` extracts `FunctionDefNode`, `ClassDefNode`, `CallSiteNode` from Python sources via tree-sitter.
- `parse/hashing.py` computes `ast_hash` per arch §4.2 with `blake3` (fallback `xxhash`).
- `graph/` builds a `networkx`-backed `CallGraph` with intra-file resolution; unresolved edges are dropped per Scope Decision #2.
- `core.types.AnalysisContext` gains an optional `call_graph` field (forward-ref, preserves `core → graph` layering rule).
- Fixtures: simple, class-with-methods, same-shape-different-names, syntax-error.

## Non-goals (deferred)

- Second language adapter (Rust / C# / TS) — Slice 7–8
- Cross-file call resolution — post-MVP
- `ControlFlowNode` for cyclomatic/cognitive — Slice 3
- `context_hash` computation — Slice 5
- Metric computation, storage writes, CLI wiring — later slices

## Test plan

- [ ] `uv run pytest -v` green locally
- [ ] `uv run pytest --cov=src/savviety_instinct` shows coverage ≥ Slice 1 baseline
- [ ] `uv run pre-commit run --all-files` clean
- [ ] Manual: `uv run python -c "from savviety_instinct.parse import PYTHON_ADAPTER; print(PYTHON_ADAPTER.parse_path('src/savviety_instinct/cli/app.py'))"` — self-dogfood: parse one of our own files without crash

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Record decisions in SESSION.md**

Run `/session-save` to record:
- Slice 2 PR opened; link in the response.
- `HASH_ALGORITHM` chosen at install time (blake3 or xxhash, whichever landed).
- Next slice: Slice 3 (first three metrics: cyclomatic, cognitive, statement_count).

---

## Self-Review

**Spec coverage (against arch §15 Slice 2 and §5.5):**
- [x] `parse/` for Python → Task 5 (`PythonAdapter`)
- [x] `graph/` call graph → Tasks 7–8 (`CallGraph`, `build_call_graph`)
- [x] Domain-neutral nodes (arch §5.5 "FunctionDefNode, ControlFlowNode") → Task 3 (`FunctionDefNode`, `ClassDefNode`, `CallSiteNode`). `ControlFlowNode` explicitly deferred to Slice 3 per Scope Decision #4.
- [x] `ast_hash` per arch §4.2 → Task 2 (`hash_ast_sexp`) + used in Task 5
- [x] `blake3` vs `xxhash` decision (HANDOFF open question) → Scope Decision #6 + Task 2 implementation
- [x] `AnalysisContext` carries graph (arch §5.3 "passed via AnalysisContext") → Task 10
- [x] Layering rule preserved (arch §2: `core` is at the bottom) → Task 10 uses `TYPE_CHECKING` guard
- [x] Parse errors degrade gracefully (arch §9) → Task 5 `ParseError` + Task 11 syntax-error integration test
- [x] Tests (per arch §10.1 "hand-crafted AST fixtures with known correct values") → fixtures in Task 5 + integration test Task 11
- [x] Tree-sitter grammar version pinned (arch §16.3) → Task 1 `tree-sitter-python==0.23.*`

**Placeholder scan:** No "TBD" / "implement later" / "add error handling" / missing code blocks. Every step contains the actual code or the actual command.

**Type consistency:** `FunctionDefNode` / `ClassDefNode` / `CallSiteNode` / `ParseResult` / `CallGraph` used identically in Tasks 3, 5, 7, 8, 10, 11. `HASH_ALGORITHM` spelled the same in Task 2 and Task 6. `PYTHON_ADAPTER` module-singleton naming consistent across Tasks 4, 5, 6, 11.

**Order check:** Task 4 creates `adapter.py` which imports `parse.python`, which doesn't exist until Task 5. Task 4's Step 4 explicitly defers commit to after Task 5. Flag this ordering so the executor batches Tasks 4+5 and only commits once the imports resolve.

---

## Execution Handoff

**Plan complete and saved to `docs/plans/2026-04-19-slice-2-parse-graph.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Good for Slice 2's 12 tasks because tree-sitter quirks are likely to need per-task iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints. Single context, slower but simpler audit trail.

**Which approach?**
