# Slice 1 — Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Single branch, no combining slices.

**Goal:** Bring Instinct's Slice 1 online: project bootstrap, package skeleton, `core/` types, `storage/` interfaces and initial schema migration, `config/` validation, and a minimal `cli/` exposing `instinct version`, `instinct init`, and "not available in this release" stubs for reserved R2+ commands.

**Architecture:** Single Python 3.12+ package (`savviety-instinct`) under `src/` layout, managed by `uv`. Twelve internal modules per arch spec §2 with strict layering (`core` pure, `storage` sole DB writer). SQLite schema per arch §4.1 managed by Alembic, including forward-compat tables (`llm_verdicts`, `patterns`, `pattern_evidence`) that are empty in MVP. Config loaded via Pydantic v2 with `scope` required (D8), `assist_level: observe`-only (R4 hook), and corporate hard-false on `sync_allowed` / `remote_apis_allowed` / `include_in_cross_project` (D5/D10).

**Tech Stack:** Python 3.12+, uv 0.9+, Typer (CLI), Rich (terminal), Pydantic v2 (config), PyYAML (config parsing), SQLAlchemy 2.x (DB), Alembic (migrations), pytest + pytest-cov (tests), ruff (lint/format), mypy (types), pre-commit (hooks).

---

## Scope Decisions (locked)

1. **CLAUDE.md is not touched in Slice 1.** Gary will handle repo CLAUDE.md separately. Do not create, delete, or edit `CLAUDE.md` or `CLAUDE.local.md`.
2. **`config/` and `cli/` are in Slice 1** because `instinct init` and `instinct version` depend on them. HANDOFF Non-goals ("no non-`core`/`storage` functionality") is read as "no `parse/graph/analyze/report/llm/curate/patterns/suggest/mcp` logic".
3. **No hashing dependency in Slice 1.** `blake3` vs `xxhash` pick is deferred to Slice 2 when hashing actually happens.
4. **Synchronous SQLAlchemy driver.** Arch §8.1 says pipeline is synchronous; use the default `sqlite3` driver, not `aiosqlite`.
5. **MVP commands not yet implemented in this slice** (`run`, `report`, `explain`, `trend`, `vacuum`, `rebuild-db`) are NOT registered with Typer. Typer's default unknown-command error is fine; later slices add them.
6. **Reserved R2+ commands** (`sync`, `curate`, `suggest`, `apply`, `serve`) ARE registered with Typer as stubs that exit non-zero with "not available in this release".
7. **SQLite runtime PRAGMAs** (`journal_mode=WAL`, `synchronous=NORMAL`) are deferred to Slice 2+ when `instinct run` opens the database. Not in Slice 1.

---

## Post-validation fixes applied (2026-04-16)

The plan went through a 4-specialist validation gate (design / dev / security / backlog). Applied fixes:

- **[Dev High]** Added `[tool.uv] default-groups = ["dev", "test"]` so `uv sync` installs `pytest` (Task 1).
- **[Dev High]** Pre-commit `mypy` switched to `repo: local` with `uv run mypy` so it sees project packages (Task 11).
- **[Dev High]** CLI tests drop the `result.stderr` fallback (would raise on default `CliRunner`); assert on `result.stdout` only (Tasks 9, 10).
- **[Design High]** `storage/interfaces.py` dataclasses reordered so `ProfileAxis` / `Observation` / `TrendPoint` precede their composite parents (prevents `get_type_hints()` NameError).
- **[Design High]** `_enforce_corporate_guardrails` rejects `llm_backend: anthropic` when `scope: corporate` (D5 hard guarantee, Task 6).
- **[Design Medium]** Added `RepoFingerprintSource` + `ProfileStatus` enums in `storage/interfaces.py`; `Profile.axes` typed `Mapping`, `Trend.points` typed `tuple[...]` (immutability tightening).
- **[Design Low]** Dropped `AnalysisContext.extras` bag; now an empty frozen dataclass. Slice 2+ adds real fields.
- **[Security Medium]** No-network fixture extended to cover `socket.create_connection`, `socket.getaddrinfo`, `socket.gethostbyname` (Task 11).
- **[Security Medium]** `.gitignore` adds SQLite WAL/SHM/journal sidecars (`.instinct/*.db-wal`, `*.db-shm`, `*.db-journal`) (Task 1).
- **[Dev Medium]** Alembic `env.py` passes `disable_existing_loggers=False` so tests keep their loggers (Task 5).
- **[Dev Medium]** Single consolidated `_enforce_corporate_guardrails` that collects all violations into one `ValueError` (Task 6, via the Design-High fix above).

Deferred (noted but not fixed this round):
- **[Design Low]** `server_default="1"` on `occurrence_count` → prefer `sa.text("1")`. String literal in SQLite is coerced; acceptable.
- **[Dev Low]** Ruff/mypy pre-commit revs may lag behind `uv sync`-installed versions; bump at execution time if needed.
- **[Security Low]** Socket fixture runs after imports — known gap; Slice 2+ will harden with `pytest-socket`.
- **[Backlog]** Repo `CLAUDE.md` from HANDOFF §89 — explicitly carved out by Gary's "ignore .claude" decision this session.

---

## File Structure

| Path | Purpose |
|------|---------|
| `pyproject.toml` | Project metadata, deps, entry points, tool configs (ruff, mypy, pytest, coverage) |
| `.python-version` | Pin Python 3.12 |
| `.gitignore` | Add Python, uv, test, and `.instinct/` entries |
| `alembic.ini` | Alembic config pointing at `src/savviety_instinct/storage/migrations` |
| `.pre-commit-config.yaml` | Pre-commit hooks: ruff-format, ruff-check, mypy |
| `src/savviety_instinct/__init__.py` | Top-level `__version__` export |
| `src/savviety_instinct/core/__init__.py` | Re-exports from `types.py` |
| `src/savviety_instinct/core/types.py` | `Artifact`, `MetricValue`, `Metric` Protocol, `Confidence`, `Language`, `ArtifactKind`, `InputKind`, `SourceRange`, `AnalysisContext` |
| `src/savviety_instinct/storage/__init__.py` | Re-exports from `interfaces.py` |
| `src/savviety_instinct/storage/interfaces.py` | `ObservationStore`, `ObservationQuery` Protocols + supporting types |
| `src/savviety_instinct/storage/migrations/env.py` | Alembic env (programmatic URL via env var) |
| `src/savviety_instinct/storage/migrations/script.py.mako` | Alembic migration template |
| `src/savviety_instinct/storage/migrations/versions/001_initial_schema.py` | Initial schema migration per arch §4.1 |
| `src/savviety_instinct/config/__init__.py` | Re-exports |
| `src/savviety_instinct/config/models.py` | Pydantic config models + validators |
| `src/savviety_instinct/config/loader.py` | `load_config`, `save_config`, `scaffold_default_config` |
| `src/savviety_instinct/cli/__init__.py` | Re-exports the Typer app |
| `src/savviety_instinct/cli/app.py` | Typer app: `version`, `init`, 5 reserved stubs |
| `src/savviety_instinct/{parse,graph,analyze,report,llm,curate,patterns,suggest,mcp}/__init__.py` | Empty skeletons (reserved modules) |
| `tests/__init__.py` | Empty |
| `tests/test_core_types.py` | Unit tests for `core/types.py` |
| `tests/test_storage_interfaces.py` | Unit tests for Protocol conformance |
| `tests/test_migration.py` | Applies migration to in-memory SQLite, inspects schema |
| `tests/test_config_models.py` | Pydantic validation tests |
| `tests/test_config_loader.py` | Load/save/scaffold tests |
| `tests/test_cli_version.py` | Typer CliRunner test for `version` |
| `tests/test_cli_init.py` | CliRunner test for `init` scaffolding + idempotency |
| `tests/test_cli_reserved.py` | CliRunner tests for 5 reserved stubs |
| `tests/test_no_network.py` | NFR-1 / AC-7 sanity: block sockets, run `instinct version` |

---

## Task 1: Project bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Modify: `.gitignore`

- [ ] **Step 1: Write `.python-version`**

Create `.python-version`:

```
3.12
```

- [ ] **Step 2: Write `pyproject.toml`**

Create `pyproject.toml`:

```toml
[project]
name = "savviety-instinct"
version = "0.1.0"
description = "Measure what matters. Learn what your team does well. Apply it."
requires-python = ">=3.12"
authors = [{ name = "Savviety" }]
dependencies = [
    "typer>=0.12,<0.13",
    "rich>=13,<14",
    "pydantic>=2.6,<3",
    "pyyaml>=6,<7",
    "sqlalchemy>=2,<3",
    "alembic>=1.13,<2",
]

[project.scripts]
instinct = "savviety_instinct.cli.app:app"
savviety-instinct = "savviety_instinct.cli.app:app"

[dependency-groups]
dev = [
    "ruff>=0.4,<1",
    "mypy>=1.10,<2",
    "types-pyyaml>=6",
    "pre-commit>=3,<5",
]
test = [
    "pytest>=8,<9",
    "pytest-cov>=5,<7",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/savviety_instinct"]

[tool.uv]
# Install dev + test groups by default. Without this, `uv sync` installs
# only `dev` and `uv run pytest` fails with "pytest: command not found".
default-groups = ["dev", "test"]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM"]
ignore = ["E501"]  # line-length handled by formatter

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = false
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = [
    "savviety_instinct.core.*",
    "savviety_instinct.storage.*",
]
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --cov=savviety_instinct --cov-report=term-missing"

[tool.coverage.run]
source = ["savviety_instinct"]
branch = true

[tool.coverage.report]
show_missing = true
```

- [ ] **Step 3: Write `.gitignore`**

Replace `.gitignore` contents with:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/

# uv
.venv/

# Test / type / lint caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
coverage.xml
htmlcov/

# Instinct runtime
.instinct/instinct.db
.instinct/*.db-wal
.instinct/*.db-shm
.instinct/*.db-journal
.instinct/reports/

# Editor (light, non-exhaustive)
.vscode/
.idea/

# Existing
CLAUDE.local.md
```

- [ ] **Step 4: Run `uv sync`**

Run: `uv sync`
Expected: creates `.venv/`, writes `uv.lock`, installs all deps in `dev` + `test` groups. Exit code 0.

- [ ] **Step 5: Verify Python version and import surface**

Run: `uv run python -c "import sys; print(sys.version_info[:3])"`
Expected: `(3, 12, X)` (patch version ≥ 0).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .python-version .gitignore uv.lock
git commit -m "build: bootstrap pyproject + uv + tool configuration"
```

---

## Task 2: Package skeleton

**Files:**
- Create: `src/savviety_instinct/__init__.py`
- Create: `src/savviety_instinct/{core,storage,parse,graph,analyze,report,config,cli,llm,curate,patterns,suggest,mcp}/__init__.py`
- Create: `src/savviety_instinct/storage/migrations/__init__.py`
- Create: `src/savviety_instinct/storage/migrations/versions/__init__.py`

- [ ] **Step 1: Create top-level package init**

Create `src/savviety_instinct/__init__.py`:

```python
"""Instinct — code intelligence and observation store."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create module skeletons**

For each of these 12 modules, create the directory and a single `__init__.py` file:

- `src/savviety_instinct/core/__init__.py`
- `src/savviety_instinct/storage/__init__.py`
- `src/savviety_instinct/parse/__init__.py`
- `src/savviety_instinct/graph/__init__.py`
- `src/savviety_instinct/analyze/__init__.py`
- `src/savviety_instinct/report/__init__.py`
- `src/savviety_instinct/config/__init__.py`
- `src/savviety_instinct/cli/__init__.py`
- `src/savviety_instinct/llm/__init__.py`
- `src/savviety_instinct/curate/__init__.py`
- `src/savviety_instinct/patterns/__init__.py`
- `src/savviety_instinct/suggest/__init__.py`
- `src/savviety_instinct/mcp/__init__.py`

Each `__init__.py` has this content (identical for all 12):

```python
"""Reserved module — see docs/04-architecture-spec.md §2."""
```

Also create two migration-tree placeholders so Alembic discovery works:

`src/savviety_instinct/storage/migrations/__init__.py`:

```python
```

`src/savviety_instinct/storage/migrations/versions/__init__.py`:

```python
```

Both files are empty. (They exist only so that Python treats them as packages, which helps test discovery and IDE navigation. Alembic itself doesn't require them, but they're harmless.)

- [ ] **Step 3: Verify package imports**

Run: `uv run python -c "import savviety_instinct; print(savviety_instinct.__version__)"`
Expected: `0.1.0`

Run: `uv run python -c "import savviety_instinct.core; import savviety_instinct.storage; import savviety_instinct.parse; import savviety_instinct.graph; import savviety_instinct.analyze; import savviety_instinct.report; import savviety_instinct.config; import savviety_instinct.cli; import savviety_instinct.llm; import savviety_instinct.curate; import savviety_instinct.patterns; import savviety_instinct.suggest; import savviety_instinct.mcp; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/
git commit -m "feat: package skeleton per arch §2 (12 modules + migrations tree)"
```

---

## Task 3: `core/types.py`

**Files:**
- Create: `src/savviety_instinct/core/types.py`
- Create: `tests/__init__.py`
- Create: `tests/test_core_types.py`

- [ ] **Step 1: Create `tests/__init__.py`**

Create `tests/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write failing test for core types**

Create `tests/test_core_types.py`:

```python
"""Tests for savviety_instinct.core.types (arch §5.1)."""

from __future__ import annotations

import pytest

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
    Metric,
    MetricValue,
    SourceRange,
)


def test_language_enum_has_mvp_languages():
    assert Language.PYTHON.value == "python"
    assert Language.RUST.value == "rust"
    assert Language.CSHARP.value == "csharp"
    assert Language.TYPESCRIPT.value == "typescript"


def test_artifact_kind_enum():
    assert {k.value for k in ArtifactKind} == {"function", "class", "module"}


def test_confidence_enum():
    assert {c.value for c in Confidence} == {"high", "medium", "low"}


def test_input_kind_enum_has_core_values():
    # InputKind is used by Metric.required_inputs. MVP metrics need at least
    # AST, call graph, and git history. Exact set can grow in later slices.
    values = {k.value for k in InputKind}
    assert {"ast", "call_graph", "git_history"}.issubset(values)


def test_source_range_is_frozen():
    r = SourceRange(file_path="x.py", line_start=1, line_end=10)
    with pytest.raises(Exception):
        r.file_path = "y.py"  # type: ignore[misc]


def test_artifact_is_frozen_and_carries_identity():
    a = Artifact(
        ast_hash="abc",
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name="foo",
        enclosing_scope=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=3),
    )
    assert a.ast_hash == "abc"
    with pytest.raises(Exception):
        a.ast_hash = "def"  # type: ignore[misc]


def test_metric_value_carries_confidence_and_version():
    mv = MetricValue(
        metric_id="cyclomatic_complexity",
        value=7,
        metric_version="0.0.0-slice1",
        confidence=Confidence.HIGH,
    )
    assert mv.confidence == Confidence.HIGH
    assert mv.notes is None


def test_analysis_context_is_constructible_with_defaults():
    ctx = AnalysisContext()
    # AnalysisContext is a forward-compat placeholder in Slice 1.
    # Slice 2+ will add call graph, imports, framework detection, etc.
    assert ctx is not None
    # Two defaults constructions are equal (frozen + no fields).
    assert AnalysisContext() == AnalysisContext()


def test_metric_protocol_runtime_checkable():
    class Dummy:
        id = "dummy"
        version = "0.0.0"
        applies_to: set[ArtifactKind] = {ArtifactKind.FUNCTION}
        required_inputs: set[InputKind] = {InputKind.AST}

        def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
            return MetricValue(
                metric_id=self.id,
                value=0,
                metric_version=self.version,
                confidence=Confidence.HIGH,
            )

    assert isinstance(Dummy(), Metric)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_core_types.py -v`
Expected: all tests fail with `ImportError` or `ModuleNotFoundError` — `savviety_instinct.core.types` does not exist yet.

- [ ] **Step 4: Implement `core/types.py`**

Create `src/savviety_instinct/core/types.py`:

```python
"""Domain types for Instinct.

Arch spec §5.1. Pure data; no I/O, no DB, no network.
Must not import from any other internal module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class Language(str, Enum):
    PYTHON = "python"
    RUST = "rust"
    CSHARP = "csharp"
    TYPESCRIPT = "typescript"


class ArtifactKind(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InputKind(str, Enum):
    AST = "ast"
    CALL_GRAPH = "call_graph"
    MODULE_GRAPH = "module_graph"
    GIT_HISTORY = "git_history"
    IMPORTS = "imports"
    TYPES = "types"


@dataclass(frozen=True, slots=True)
class SourceRange:
    file_path: str
    line_start: int
    line_end: int


@dataclass(frozen=True, slots=True)
class Artifact:
    ast_hash: str
    language: Language
    kind: ArtifactKind
    name: str
    enclosing_scope: str | None
    source_range: SourceRange


@dataclass(frozen=True, slots=True)
class MetricValue:
    metric_id: str
    value: float | int | str
    metric_version: str
    confidence: Confidence
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Context passed to each Metric.compute().

    Slice 1: placeholder with no fields. Slice 2+ will add call graph,
    module graph, import set, framework indicators, etc. per arch §5.3,
    using keyword-only fields with defaults so construction stays compatible.
    """


@runtime_checkable
class Metric(Protocol):
    id: str
    version: str
    applies_to: set[ArtifactKind]
    required_inputs: set[InputKind]

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue: ...
```

Also update `src/savviety_instinct/core/__init__.py` to re-export:

```python
"""Core domain types — pure, no I/O."""

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
    Metric,
    MetricValue,
    SourceRange,
)

__all__ = [
    "AnalysisContext",
    "Artifact",
    "ArtifactKind",
    "Confidence",
    "InputKind",
    "Language",
    "Metric",
    "MetricValue",
    "SourceRange",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_core_types.py -v`
Expected: all 9 tests pass.

- [ ] **Step 6: Run mypy on `core/`**

Run: `uv run mypy src/savviety_instinct/core`
Expected: `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/core/ tests/__init__.py tests/test_core_types.py
git commit -m "feat(core): domain types per arch §5.1"
```

---

## Task 4: `storage/interfaces.py`

**Files:**
- Create: `src/savviety_instinct/storage/interfaces.py`
- Create: `tests/test_storage_interfaces.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_storage_interfaces.py`:

```python
"""Tests for savviety_instinct.storage.interfaces (arch §5.2)."""

from __future__ import annotations

from datetime import datetime

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    MetricValue,
    SourceRange,
)
from savviety_instinct.storage.interfaces import (
    FileLocation,
    ObservationQuery,
    ObservationStore,
    Profile,
    Ranking,
    RepoFingerprintSource,
    Run,
    RunMeta,
    RunStatus,
    Trend,
)


def _sample_artifact() -> Artifact:
    return Artifact(
        ast_hash="h1",
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name="foo",
        enclosing_scope=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=5),
    )


def test_run_status_values():
    assert {s.value for s in RunStatus} == {"running", "completed", "failed"}


def test_repo_fingerprint_source_values():
    assert {s.value for s in RepoFingerprintSource} == {
        "first_commit",
        "origin_url",
        "synthetic",
    }


def test_run_meta_is_frozen_dataclass():
    m = RunMeta(
        repo_fingerprint="fp",
        repo_fingerprint_source=RepoFingerprintSource.FIRST_COMMIT,
        started_at=datetime(2026, 4, 16, 12, 0, 0),
        commit_sha="abc123",
        branch="main",
        config_hash="ch",
        tool_version="0.1.0",
        metric_version="0.0.0-slice1",
    )
    assert m.commit_sha == "abc123"


def test_file_location_fields():
    loc = FileLocation(
        file_path="x.py",
        line_start=1,
        line_end=5,
        symbol_name="foo",
        enclosing_scope=None,
        context_hash="ctx",
    )
    assert loc.context_hash == "ctx"


class _FakeStore:
    """Minimal stub that satisfies the ObservationStore Protocol shape."""

    def __init__(self) -> None:
        self.runs: dict[int, RunMeta] = {}

    def begin_run(self, meta: RunMeta) -> int:
        run_id = len(self.runs) + 1
        self.runs[run_id] = meta
        return run_id

    def complete_run(self, run_id: int, status: RunStatus) -> None:
        _ = (run_id, status)

    def upsert_artifact(self, artifact: Artifact, metrics: list[MetricValue]) -> int:
        _ = (artifact, metrics)
        return 1

    def record_observation(
        self, run_id: int, artifact_id: int, location: FileLocation
    ) -> None:
        _ = (run_id, artifact_id, location)

    def write_ranking(self, run_id: int, ranking: Ranking) -> None:
        _ = (run_id, ranking)

    def write_profile(self, run_id: int, profile: Profile) -> None:
        _ = (run_id, profile)


class _FakeQuery:
    def get_run(self, run_id: int) -> Run:
        raise NotImplementedError

    def get_rankings(self, run_id: int, limit: int) -> list[object]:
        return []

    def get_profile(self, run_id: int) -> Profile:
        raise NotImplementedError

    def get_trend(self, window_days: int) -> Trend:
        raise NotImplementedError

    def get_artifact_history(self, ast_hash: str) -> list[object]:
        return []


def test_fake_store_satisfies_protocol():
    assert isinstance(_FakeStore(), ObservationStore)


def test_fake_query_satisfies_protocol():
    assert isinstance(_FakeQuery(), ObservationQuery)


def test_begin_run_roundtrip():
    store = _FakeStore()
    run_id = store.begin_run(
        RunMeta(
            repo_fingerprint="fp",
            repo_fingerprint_source=RepoFingerprintSource.SYNTHETIC,
            started_at=datetime.now(),
            commit_sha=None,
            branch=None,
            config_hash="ch",
            tool_version="0.1.0",
            metric_version="0.0.0-slice1",
        )
    )
    assert run_id == 1
    assert store.runs[1].repo_fingerprint == "fp"


def test_upsert_artifact_returns_id():
    store = _FakeStore()
    aid = store.upsert_artifact(
        _sample_artifact(),
        [
            MetricValue(
                metric_id="m",
                value=0,
                metric_version="0.0.0-slice1",
                confidence=Confidence.HIGH,
            )
        ],
    )
    assert aid == 1
    # silence unused-import lint for AnalysisContext
    _ = AnalysisContext()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage_interfaces.py -v`
Expected: all tests fail with `ImportError` or `ModuleNotFoundError` — `savviety_instinct.storage.interfaces` does not exist yet.

- [ ] **Step 3: Implement `storage/interfaces.py`**

Create `src/savviety_instinct/storage/interfaces.py`:

```python
"""Storage layer Protocols — the only module that knows about SQL.

Arch spec §5.2. Concrete SQLAlchemy implementation lands in Slice 2+.
Slice 1 defines the Protocols + data types so higher layers can depend on
interfaces, not implementations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from savviety_instinct.core.types import Artifact, MetricValue

RunId = int
ArtifactId = int


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RepoFingerprintSource(str, Enum):
    """Three derivation tiers per D10. Populated on `runs.repo_fingerprint_source`."""

    FIRST_COMMIT = "first_commit"
    ORIGIN_URL = "origin_url"
    SYNTHETIC = "synthetic"


class ProfileStatus(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    ELEVATED = "elevated"


@dataclass(frozen=True, slots=True)
class RunMeta:
    repo_fingerprint: str
    repo_fingerprint_source: RepoFingerprintSource
    started_at: datetime
    commit_sha: str | None
    branch: str | None
    config_hash: str
    tool_version: str
    metric_version: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class FileLocation:
    file_path: str
    line_start: int
    line_end: int
    symbol_name: str
    enclosing_scope: str | None
    context_hash: str  # D6 forward-compat: dedicated column on run_observations


@dataclass(frozen=True, slots=True)
class Ranking:
    run_observation_id: int
    attention_priority: float
    rank: int
    contributing_metrics_json: str


@dataclass(frozen=True, slots=True)
class ProfileAxis:
    name: str
    p50: float | None
    p90: float | None
    p95: float | None
    p99: float | None
    status: ProfileStatus
    sample_size: int


@dataclass(frozen=True, slots=True)
class Profile:
    axes: Mapping[str, ProfileAxis]


@dataclass(frozen=True, slots=True)
class Run:
    id: int
    meta: RunMeta
    completed_at: datetime | None
    status: RunStatus


@dataclass(frozen=True, slots=True)
class Observation:
    run_id: int
    artifact_id: int
    file_location: FileLocation


@dataclass(frozen=True, slots=True)
class RankedObservation:
    run_observation_id: int
    artifact_id: int
    file_location: FileLocation
    ranking: Ranking


@dataclass(frozen=True, slots=True)
class TrendPoint:
    run_id: int
    at: datetime
    axis: str
    value: float


@dataclass(frozen=True, slots=True)
class Trend:
    window_days: int
    points: tuple[TrendPoint, ...]


@runtime_checkable
class ObservationStore(Protocol):
    def begin_run(self, meta: RunMeta) -> RunId: ...
    def complete_run(self, run_id: RunId, status: RunStatus) -> None: ...
    def upsert_artifact(
        self, artifact: Artifact, metrics: list[MetricValue]
    ) -> ArtifactId: ...
    def record_observation(
        self, run_id: RunId, artifact_id: ArtifactId, location: FileLocation
    ) -> None: ...
    def write_ranking(self, run_id: RunId, ranking: Ranking) -> None: ...
    def write_profile(self, run_id: RunId, profile: Profile) -> None: ...


@runtime_checkable
class ObservationQuery(Protocol):
    def get_run(self, run_id: RunId) -> Run: ...
    def get_rankings(self, run_id: RunId, limit: int) -> list[RankedObservation]: ...
    def get_profile(self, run_id: RunId) -> Profile: ...
    def get_trend(self, window_days: int) -> Trend: ...
    def get_artifact_history(self, ast_hash: str) -> list[Observation]: ...
```

Update `src/savviety_instinct/storage/__init__.py`:

```python
"""Storage layer — repository pattern Protocols and (Slice 2+) SQLAlchemy impl."""

from savviety_instinct.storage.interfaces import (
    ArtifactId,
    FileLocation,
    Observation,
    ObservationQuery,
    ObservationStore,
    Profile,
    ProfileAxis,
    ProfileStatus,
    Ranking,
    RankedObservation,
    RepoFingerprintSource,
    Run,
    RunId,
    RunMeta,
    RunStatus,
    Trend,
    TrendPoint,
)

__all__ = [
    "ArtifactId",
    "FileLocation",
    "Observation",
    "ObservationQuery",
    "ObservationStore",
    "Profile",
    "ProfileAxis",
    "ProfileStatus",
    "Ranking",
    "RankedObservation",
    "RepoFingerprintSource",
    "Run",
    "RunId",
    "RunMeta",
    "RunStatus",
    "Trend",
    "TrendPoint",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_storage_interfaces.py -v`
Expected: all 8 tests pass.

- [ ] **Step 5: Run mypy on `storage/`**

Run: `uv run mypy src/savviety_instinct/storage`
Expected: `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/storage/ tests/test_storage_interfaces.py
git commit -m "feat(storage): repository protocol interfaces per arch §5.2"
```

---

## Task 5: Alembic init + initial schema migration

**Files:**
- Create: `alembic.ini`
- Create: `src/savviety_instinct/storage/migrations/env.py`
- Create: `src/savviety_instinct/storage/migrations/script.py.mako`
- Create: `src/savviety_instinct/storage/migrations/versions/001_initial_schema.py`
- Create: `tests/test_migration.py`

- [ ] **Step 1: Write failing migration test**

Create `tests/test_migration.py`:

```python
"""Tests for the initial schema migration (arch §4.1)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture()
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Apply the initial migration to a fresh SQLite file and yield the URL."""

    db_path = tmp_path / "instinct.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("INSTINCT_DB_URL", url)

    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return url


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    return set(inspect(engine).get_table_names())


def _indexes(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def _columns(url: str, table: str) -> set[str]:
    engine = create_engine(url)
    return {col["name"] for col in inspect(engine).get_columns(table)}


def test_migration_creates_all_tables(migrated_db: str):
    tables = _tables(migrated_db)
    assert {
        "runs",
        "observation_artifacts",
        "run_observations",
        "rankings",
        "run_profiles",
        "llm_verdicts",
        "patterns",
        "pattern_evidence",
    }.issubset(tables)


def test_runs_has_repo_fingerprint_columns(migrated_db: str):
    cols = _columns(migrated_db, "runs")
    assert "repo_fingerprint" in cols
    assert "repo_fingerprint_source" in cols


def test_observation_artifacts_has_repo_fingerprint(migrated_db: str):
    cols = _columns(migrated_db, "observation_artifacts")
    assert "repo_fingerprint" in cols


def test_run_observations_has_context_hash(migrated_db: str):
    cols = _columns(migrated_db, "run_observations")
    assert "context_hash" in cols, "D6: dedicated context_hash column on run_observations"


def test_expected_indexes_exist(migrated_db: str):
    assert "idx_runs_fingerprint" in _indexes(migrated_db, "runs")
    art_idx = _indexes(migrated_db, "observation_artifacts")
    assert {"idx_artifacts_ast_hash", "idx_artifacts_stability", "idx_artifacts_fingerprint"}.issubset(
        art_idx
    )
    obs_idx = _indexes(migrated_db, "run_observations")
    assert {
        "idx_run_obs_run",
        "idx_run_obs_artifact",
        "idx_run_obs_file",
        "idx_run_obs_context",
    }.issubset(obs_idx)
    assert "idx_rankings_run" in _indexes(migrated_db, "rankings")


def test_pattern_tables_exist_empty(migrated_db: str):
    engine = create_engine(migrated_db)
    with engine.connect() as conn:
        from sqlalchemy import text

        patterns_count = conn.execute(text("SELECT COUNT(*) FROM patterns")).scalar()
        evidence_count = conn.execute(text("SELECT COUNT(*) FROM pattern_evidence")).scalar()
    assert patterns_count == 0
    assert evidence_count == 0
    _ = os.getenv  # keep import
```

- [ ] **Step 2: Write `alembic.ini`**

Create `alembic.ini` at repo root:

```ini
[alembic]
script_location = src/savviety_instinct/storage/migrations
sqlalchemy.url = sqlite:///.instinct/instinct.db
file_template = %%(rev)s_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Write `env.py`**

Create `src/savviety_instinct/storage/migrations/env.py`:

```python
"""Alembic environment.

Reads SQLAlchemy URL from the alembic config (set by alembic.ini or by
the caller via `command.upgrade(cfg, "head")`). For in-test use, the test
fixture overrides `sqlalchemy.url` programmatically.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False so this doesn't silently suppress
    # pytest / app loggers for the rest of the process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Allow environment variable override (useful for CI / tests).
env_url = os.getenv("INSTINCT_DB_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

# Slice 1 does not expose a SQLAlchemy metadata object — migrations are
# hand-written using the `op` API. `target_metadata = None` disables
# autogeneration.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Write `script.py.mako`**

Create `src/savviety_instinct/storage/migrations/script.py.mako`:

```
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Write the initial schema migration**

Create `src/savviety_instinct/storage/migrations/versions/001_initial_schema.py`:

```python
"""Initial schema — arch §4.1.

Creates all MVP tables plus forward-compat reservations:
- `llm_verdicts` (R2 hook, empty in MVP per §12)
- `patterns`, `pattern_evidence` (R3 hooks, empty in MVP per §11 / §12)

`repo_fingerprint` columns on `runs` and `observation_artifacts` per D10
enable the R2+ Postgres warehouse aggregation. `context_hash` on
`run_observations` is a dedicated column per D6.

Revision ID: 001
Revises:
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_fingerprint", sa.Text, nullable=False),
        sa.Column("repo_fingerprint_source", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("commit_sha", sa.Text, nullable=True),
        sa.Column("branch", sa.Text, nullable=True),
        sa.Column("config_hash", sa.Text, nullable=False),
        sa.Column("tool_version", sa.Text, nullable=False),
        sa.Column("metric_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_runs_fingerprint", "runs", ["repo_fingerprint"])

    op.create_table(
        "observation_artifacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repo_fingerprint", sa.Text, nullable=False),
        sa.Column("ast_hash", sa.Text, nullable=False),
        sa.Column("language", sa.Text, nullable=False),
        sa.Column("artifact_kind", sa.Text, nullable=False),
        sa.Column("ast_serialized", sa.LargeBinary, nullable=True),
        sa.Column("metrics_json", sa.Text, nullable=False),
        sa.Column("metric_version", sa.Text, nullable=False),
        sa.Column(
            "first_seen_run_id",
            sa.Integer,
            sa.ForeignKey("runs.id"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_run_id",
            sa.Integer,
            sa.ForeignKey("runs.id"),
            nullable=False,
        ),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("stability_tier", sa.Text, nullable=False),
        sa.UniqueConstraint("ast_hash", "language", "metric_version"),
    )
    op.create_index("idx_artifacts_ast_hash", "observation_artifacts", ["ast_hash"])
    op.create_index(
        "idx_artifacts_stability", "observation_artifacts", ["stability_tier"]
    )
    op.create_index(
        "idx_artifacts_fingerprint", "observation_artifacts", ["repo_fingerprint"]
    )

    op.create_table(
        "run_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.Integer,
            sa.ForeignKey("observation_artifacts.id"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("line_start", sa.Integer, nullable=False),
        sa.Column("line_end", sa.Integer, nullable=False),
        sa.Column("symbol_name", sa.Text, nullable=False),
        sa.Column("enclosing_scope", sa.Text, nullable=True),
        sa.Column("context_hash", sa.Text, nullable=False),
    )
    op.create_index("idx_run_obs_run", "run_observations", ["run_id"])
    op.create_index("idx_run_obs_artifact", "run_observations", ["artifact_id"])
    op.create_index("idx_run_obs_file", "run_observations", ["file_path"])
    op.create_index("idx_run_obs_context", "run_observations", ["context_hash"])

    op.create_table(
        "rankings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_observation_id",
            sa.Integer,
            sa.ForeignKey("run_observations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attention_priority", sa.Float, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("contributing_metrics_json", sa.Text, nullable=False),
    )
    op.create_index("idx_rankings_run", "rankings", ["run_id", "rank"])

    op.create_table(
        "run_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("axis", sa.Text, nullable=False),
        sa.Column("p50", sa.Float, nullable=True),
        sa.Column("p90", sa.Float, nullable=True),
        sa.Column("p95", sa.Float, nullable=True),
        sa.Column("p99", sa.Float, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False),
    )

    op.create_table(
        "llm_verdicts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "artifact_id",
            sa.Integer,
            sa.ForeignKey("observation_artifacts.id"),
            nullable=False,
        ),
        sa.Column("context_hash", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("prompt_hash", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("artifact_id", "context_hash", "model_id", "prompt_hash"),
    )

    op.create_table(
        "patterns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pattern_id", sa.Text, nullable=False, unique=True),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("structural_sig", sa.Text, nullable=True),
        sa.Column(
            "lifecycle_state", sa.Text, nullable=False, server_default="proposed"
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "pattern_evidence",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "pattern_id", sa.Integer, sa.ForeignKey("patterns.id"), nullable=False
        ),
        sa.Column(
            "artifact_id",
            sa.Integer,
            sa.ForeignKey("observation_artifacts.id"),
            nullable=False,
        ),
        sa.Column(
            "run_id", sa.Integer, sa.ForeignKey("runs.id"), nullable=True
        ),
        sa.Column("relation", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_pattern_evidence_pattern", "pattern_evidence", ["pattern_id"])
    op.create_index(
        "idx_pattern_evidence_artifact", "pattern_evidence", ["artifact_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_pattern_evidence_artifact", table_name="pattern_evidence")
    op.drop_index("idx_pattern_evidence_pattern", table_name="pattern_evidence")
    op.drop_table("pattern_evidence")
    op.drop_table("patterns")
    op.drop_table("llm_verdicts")
    op.drop_table("run_profiles")
    op.drop_index("idx_rankings_run", table_name="rankings")
    op.drop_table("rankings")
    op.drop_index("idx_run_obs_context", table_name="run_observations")
    op.drop_index("idx_run_obs_file", table_name="run_observations")
    op.drop_index("idx_run_obs_artifact", table_name="run_observations")
    op.drop_index("idx_run_obs_run", table_name="run_observations")
    op.drop_table("run_observations")
    op.drop_index("idx_artifacts_fingerprint", table_name="observation_artifacts")
    op.drop_index("idx_artifacts_stability", table_name="observation_artifacts")
    op.drop_index("idx_artifacts_ast_hash", table_name="observation_artifacts")
    op.drop_table("observation_artifacts")
    op.drop_index("idx_runs_fingerprint", table_name="runs")
    op.drop_table("runs")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_migration.py -v`
Expected: all 6 tests pass. Schema has all 8 tables, repo_fingerprint on the two required tables, context_hash on run_observations, and all expected indexes.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini src/savviety_instinct/storage/migrations/ tests/test_migration.py
git commit -m "feat(storage): initial schema migration per arch §4.1"
```

---

## Task 6: `config/models.py`

**Files:**
- Create: `src/savviety_instinct/config/models.py`
- Create: `tests/test_config_models.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_config_models.py`:

```python
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
    assert cfg.sync_allowed is False
    assert cfg.remote_apis_allowed is False


def test_unknown_keys_rejected():
    # arch §16.5: unknown keys are errors by default (strict).
    with pytest.raises(ValidationError):
        InstinctConfig.model_validate(
            {"scope": "personal", "not_a_real_key": "boom"}
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_models.py -v`
Expected: all tests fail with `ImportError` — the module does not exist yet.

- [ ] **Step 3: Implement `config/models.py`**

Create `src/savviety_instinct/config/models.py`:

```python
"""Pydantic v2 config models for .instinct/config.yaml.

Decisions enforced:
- D5: corporate scope → remote_apis_allowed hard-false
- D8: scope is required; no default
- D10: corporate scope → sync_allowed hard-false;
       corporate scope → include_in_cross_project hard-false
- R4 hook: assist_level must be "observe" in MVP (any other value is a
  validation error)
- arch §16.5: unknown keys are rejected (extra="forbid")
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class Scope(str, Enum):
    PERSONAL = "personal"
    CORPORATE = "corporate"
    OPEN_SOURCE = "open-source"


class AssistLevel(str, Enum):
    OBSERVE = "observe"
    SUGGEST = "suggest"
    PATCH_ASSIST = "patch_assist"
    APPLY = "apply"


class LlmBackend(str, Enum):
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

    @model_validator(mode="after")
    def _enforce_mvp_assist_level(self) -> "InstinctConfig":
        if self.assist_level is not AssistLevel.OBSERVE:
            raise ValueError(
                f"assist_level must be 'observe' in MVP (got {self.assist_level.value!r}); "
                "other levels are reserved for Release 4."
            )
        return self

    @model_validator(mode="after")
    def _enforce_corporate_guardrails(self) -> "InstinctConfig":
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
```

Update `src/savviety_instinct/config/__init__.py`:

```python
"""Config loading, validation, and scaffolding."""

from savviety_instinct.config.models import (
    AssistLevel,
    InstinctConfig,
    LlmBackend,
    Scope,
)

__all__ = ["AssistLevel", "InstinctConfig", "LlmBackend", "Scope"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_models.py -v`
Expected: all 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/config/ tests/test_config_models.py
git commit -m "feat(config): pydantic models with D5/D8/D10 guardrails"
```

---

## Task 7: `config/loader.py`

**Files:**
- Create: `src/savviety_instinct/config/loader.py`
- Create: `tests/test_config_loader.py`
- Modify: `src/savviety_instinct/config/__init__.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_config_loader.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: fails — `savviety_instinct.config.loader` does not exist.

- [ ] **Step 3: Implement `config/loader.py`**

Create `src/savviety_instinct/config/loader.py`:

```python
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
```

Update `src/savviety_instinct/config/__init__.py`:

```python
"""Config loading, validation, and scaffolding."""

from savviety_instinct.config.loader import (
    ConfigFileError,
    load_config,
    save_config,
    scaffold_default_config,
)
from savviety_instinct.config.models import (
    AssistLevel,
    InstinctConfig,
    LlmBackend,
    Scope,
)

__all__ = [
    "AssistLevel",
    "ConfigFileError",
    "InstinctConfig",
    "LlmBackend",
    "Scope",
    "load_config",
    "save_config",
    "scaffold_default_config",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_loader.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/config/ tests/test_config_loader.py
git commit -m "feat(config): yaml loader + scaffold template"
```

---

## Task 8: `cli/app.py` — `instinct version`

**Files:**
- Create: `src/savviety_instinct/cli/app.py`
- Create: `tests/test_cli_version.py`
- Modify: `src/savviety_instinct/cli/__init__.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_cli_version.py`:

```python
"""Tests for `instinct version`."""

from __future__ import annotations

from typer.testing import CliRunner

from savviety_instinct import __version__
from savviety_instinct.cli.app import app

runner = CliRunner()


def test_version_prints_tool_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_mentions_metrics_section():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    # In Slice 1 no metrics are registered; version should still list a
    # metrics section so the output shape is stable as metrics land.
    assert "metric" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_version.py -v`
Expected: fails — `savviety_instinct.cli.app` does not exist.

- [ ] **Step 3: Implement the CLI app and `version`**

Create `src/savviety_instinct/cli/app.py`:

```python
"""Instinct CLI (Typer).

Slice 1 surface:
    instinct version   — print tool and metric versions
    instinct init      — scaffold .instinct/config.yaml and .gitignore entries
    instinct sync      — R2 reserved; prints "not available in this release"
    instinct curate    — R3 reserved
    instinct suggest   — R4 reserved
    instinct apply     — R4 reserved
    instinct serve     — R5 reserved (MCP)

MVP commands that are not yet implemented in this slice (`run`, `report`,
`explain`, `trend`, `vacuum`, `rebuild-db`) are intentionally NOT registered;
Typer's default unknown-command error is sufficient.
"""

from __future__ import annotations

import typer

from savviety_instinct import __version__

app = typer.Typer(
    name="instinct",
    help="Instinct — measure what matters. Learn what your team does well. Apply it.",
    no_args_is_help=True,
    add_completion=False,
)


# Slice 1 has no registered metrics. Later slices append to this dict as
# they register their metrics (metric_id -> metric_version).
REGISTERED_METRIC_VERSIONS: dict[str, str] = {}


@app.command("version")
def version_cmd() -> None:
    """Print tool and metric versions."""
    typer.echo(f"instinct {__version__}")
    if REGISTERED_METRIC_VERSIONS:
        typer.echo("metrics:")
        for metric_id, version in sorted(REGISTERED_METRIC_VERSIONS.items()):
            typer.echo(f"  {metric_id}: {version}")
    else:
        typer.echo("metrics: (none registered)")
```

Update `src/savviety_instinct/cli/__init__.py`:

```python
"""CLI entry point (Typer)."""

from savviety_instinct.cli.app import app

__all__ = ["app"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_version.py -v`
Expected: both tests pass.

- [ ] **Step 5: Verify the installed entry point works**

Run: `uv run instinct version`
Expected stdout:

```
instinct 0.1.0
metrics: (none registered)
```

Exit code 0.

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/cli/ tests/test_cli_version.py
git commit -m "feat(cli): instinct version"
```

---

## Task 9: `cli/app.py` — `instinct init`

**Files:**
- Modify: `src/savviety_instinct/cli/app.py`
- Create: `tests/test_cli_init.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_cli_init.py`:

```python
"""Tests for `instinct init`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from savviety_instinct.cli.app import app

runner = CliRunner()


def _run_init_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str):
    monkeypatch.chdir(tmp_path)
    return runner.invoke(app, ["init", *args])


def test_init_creates_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0, result.stdout
    config_path = tmp_path / ".instinct" / "config.yaml"
    assert config_path.exists()
    assert "scope: personal" in config_path.read_text()


def test_init_appends_gitignore_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".gitignore").write_text("# existing\n")
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".instinct/instinct.db" in gitignore
    assert ".instinct/reports/" in gitignore
    # Existing content preserved.
    assert "# existing" in gitignore


def test_init_creates_gitignore_if_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".instinct/instinct.db" in gitignore


def test_init_is_idempotent_on_gitignore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".gitignore").write_text(".instinct/instinct.db\n.instinct/reports/\n")
    # Remove config so init does its other work.
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code == 0
    content = (tmp_path / ".gitignore").read_text()
    # Entries appear exactly once each.
    assert content.count(".instinct/instinct.db") == 1
    assert content.count(".instinct/reports/") == 1


def test_init_refuses_when_config_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".instinct").mkdir()
    (tmp_path / ".instinct" / "config.yaml").write_text("scope: personal\n")
    result = _run_init_in(tmp_path, monkeypatch)
    assert result.exit_code != 0
    # Default CliRunner merges stderr into stdout; assert on stdout only.
    assert "exists" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_init.py -v`
Expected: all 5 tests fail — `init` command not defined.

- [ ] **Step 3: Implement `instinct init`**

Append to `src/savviety_instinct/cli/app.py`:

```python
from pathlib import Path

from savviety_instinct.config.loader import (
    ConfigFileError,
    scaffold_default_config,
)

GITIGNORE_ENTRIES: tuple[str, ...] = (
    ".instinct/instinct.db",
    ".instinct/reports/",
)


def _ensure_gitignore_entries(gitignore_path: Path, entries: tuple[str, ...]) -> None:
    """Append each entry to .gitignore if not already present. Creates file if missing."""
    existing = gitignore_path.read_text() if gitignore_path.exists() else ""
    existing_lines = {line.strip() for line in existing.splitlines()}
    missing = [e for e in entries if e not in existing_lines]
    if not missing:
        return
    # Ensure a trailing newline before appending.
    if existing and not existing.endswith("\n"):
        existing += "\n"
    appended = existing + "\n".join(missing) + "\n"
    gitignore_path.write_text(appended)


@app.command("init")
def init_cmd() -> None:
    """Scaffold .instinct/config.yaml and add runtime paths to .gitignore."""
    cwd = Path.cwd()
    config_path = cwd / ".instinct" / "config.yaml"
    try:
        scaffold_default_config(config_path)
    except ConfigFileError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    _ensure_gitignore_entries(cwd / ".gitignore", GITIGNORE_ENTRIES)
    typer.echo(f"Scaffolded {config_path.relative_to(cwd)}")
    typer.echo("Updated .gitignore with Instinct runtime paths.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_init.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/cli/app.py tests/test_cli_init.py
git commit -m "feat(cli): instinct init scaffolds config + gitignore entries"
```

---

## Task 10: Reserved command stubs

**Files:**
- Modify: `src/savviety_instinct/cli/app.py`
- Create: `tests/test_cli_reserved.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_cli_reserved.py`:

```python
"""Tests for reserved R2+ command stubs (arch §7)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from savviety_instinct.cli.app import app

runner = CliRunner()

RESERVED_COMMANDS = ["sync", "curate", "suggest", "apply", "serve"]


@pytest.mark.parametrize("cmd", RESERVED_COMMANDS)
def test_reserved_command_exits_nonzero_with_message(cmd: str):
    result = runner.invoke(app, [cmd])
    assert result.exit_code == 2, f"{cmd} returned exit code {result.exit_code}"
    # Default CliRunner merges stderr into stdout; assert on stdout only.
    assert "not available" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_reserved.py -v`
Expected: all 5 parametrized cases fail — commands don't exist yet.

- [ ] **Step 3: Implement the 5 stubs**

Append to `src/savviety_instinct/cli/app.py`:

```python
_RESERVED_COMMAND_MESSAGE_FMT = (
    "Command '{cmd}' is not available in this release. "
    "See docs/04-architecture-spec.md §7 for the release roadmap."
)


def _reserved(cmd: str) -> None:
    typer.echo(_RESERVED_COMMAND_MESSAGE_FMT.format(cmd=cmd), err=True)
    raise typer.Exit(code=2)


@app.command("sync")
def sync_cmd() -> None:
    """Reserved (R2): push observations to the Postgres warehouse."""
    _reserved("sync")


@app.command("curate")
def curate_cmd() -> None:
    """Reserved (R3): pattern curation."""
    _reserved("curate")


@app.command("suggest")
def suggest_cmd() -> None:
    """Reserved (R4): suggestion generation."""
    _reserved("suggest")


@app.command("apply")
def apply_cmd() -> None:
    """Reserved (R4): apply suggested changes."""
    _reserved("apply")


@app.command("serve")
def serve_cmd() -> None:
    """Reserved (R5): MCP server."""
    _reserved("serve")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_reserved.py -v`
Expected: all 5 cases pass.

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/cli/app.py tests/test_cli_reserved.py
git commit -m "feat(cli): reserved R2+ command stubs per arch §7"
```

---

## Task 11: Pre-commit hooks + NFR-1 no-network sanity test

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `tests/test_no_network.py`

- [ ] **Step 1: Write failing no-network test**

Create `tests/test_no_network.py`:

```python
"""NFR-1 / AC-7 sanity: Slice 1 Instinct CLI opens no outbound sockets.

Slice 1 does not exercise `instinct run`, so this test covers only the
commands available now (`version`, `init`, and the reserved stubs).
Slice 2+ will extend this with a full `instinct run` coverage.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from savviety_instinct.cli.app import app


class _NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _block_outbound_sockets(monkeypatch: pytest.MonkeyPatch):
    """Refuse every common outbound-network entry point in stdlib.

    Covers raw sockets, `socket.create_connection`, DNS resolution, and
    `gethostbyname`. Higher-level libraries (urllib, http.client, requests)
    all funnel through one of these.

    Slice 1 caveat: this fixture runs at test-setup, so any phone-home at
    module-import time would sneak through. No MVP dep is known to do that;
    Slice 2+ will harden with pytest-socket and a subprocess smoke test.
    """

    def _refuse(*args: object, **kwargs: object) -> None:
        raise _NetworkBlocked(f"outbound network blocked: args={args!r}")

    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket, "gethostbyname", _refuse)

    real_socket = socket.socket

    class BlockingSocket(real_socket):
        def connect(self, *args, **kwargs):
            _refuse(*args, **kwargs)

        def connect_ex(self, *args, **kwargs):
            _refuse(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", BlockingSocket)
    yield


runner = CliRunner()


def test_version_opens_no_sockets():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "instinct" in result.stdout.lower()


def test_init_opens_no_sockets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / ".instinct" / "config.yaml").exists()


def test_reserved_command_opens_no_sockets():
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 2
```

- [ ] **Step 2: Run the no-network test**

Run: `uv run pytest tests/test_no_network.py -v`
Expected: all 3 tests pass (Slice 1 commands are pure local — no socket calls).

- [ ] **Step 3: Write `.pre-commit-config.yaml`**

Create `.pre-commit-config.yaml`:

```yaml
# Pre-commit hooks — arch §3.2.
# Ruff for lint + format; mypy for core/ and storage/ (strict per pyproject.toml).
#
# mypy runs as a `local` hook via `uv run mypy` so it sees the project's own
# packages (otherwise pre-commit's isolated mypy env cannot resolve
# `savviety_instinct.core.types` imports from `storage/interfaces.py`).
# Ruff revs should match what `uv sync` installs — bump as needed.
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy (core + storage, strict)
        entry: uv run mypy
        language: system
        types: [python]
        files: ^src/savviety_instinct/(core|storage)/
        pass_filenames: true
```

- [ ] **Step 4: Install and run hooks**

Run: `uv run pre-commit install`
Expected: `pre-commit installed at .git/hooks/pre-commit`.

Run: `uv run pre-commit run --all-files`
Expected: ruff-format applies formatting (auto-fixable), ruff lint passes or auto-fixes, mypy passes on `core/` and `storage/`. If ruff auto-formats any files, re-run `uv run pre-commit run --all-files` to confirm a clean pass.

If any file was modified by ruff-format, stage it:

Run: `git add -A`

- [ ] **Step 5: Full test sweep**

Run: `uv run pytest`
Expected: all tests across all files pass. Coverage report prints at the end.

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml tests/test_no_network.py
git commit -m "build: pre-commit hooks + NFR-1 no-network sanity test"
```

---

## Final verification checklist

After all 11 tasks complete, run a clean verification:

- [ ] `uv sync` (clean install)
- [ ] `uv run pytest` — all tests pass
- [ ] `uv run mypy src/savviety_instinct/core src/savviety_instinct/storage` — no issues
- [ ] `uv run ruff check` — no issues
- [ ] `uv run ruff format --check` — no diffs
- [ ] `uv run instinct version` → prints `instinct 0.1.0` + `metrics: (none registered)`
- [ ] `uv run instinct init` in a scratch directory → creates `.instinct/config.yaml` + updates `.gitignore`
- [ ] `uv run instinct sync` → exits 2 with "not available in this release"
- [ ] `git log --oneline` — one commit per task (11 new commits beyond the original three doc commits)

---

## What this slice intentionally does NOT do

- No parsing (`parse/` is an empty module)
- No metric computation (`analyze/` is empty)
- No reports (`report/` is empty)
- No git history integration
- No hashing (blake3/xxhash pick deferred to Slice 2)
- No SQLite runtime pragmas (journal_mode=WAL, synchronous=NORMAL — Slice 2+)
- No repo_fingerprint *computation* (only the schema columns that will store it in Slice 2+)
- No `instinct run` / `report` / `explain` / `trend` / `vacuum` / `rebuild-db` commands (later slices)
- No repo `CLAUDE.md` changes (Gary handles separately)

These are deliberate scope boundaries, not oversights. Do not expand them in this slice.
