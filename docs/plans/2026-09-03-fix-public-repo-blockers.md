# Fix Public-Repo Blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Source:** 2026-09-03 deep review, §2 "Ship-blockers in the public repo" (report: https://claude.ai/code/artifact/cc8c92e6-b995-49e5-8a46-a14008394dc7). All four reproduced on a clean clone of master @ `6c73a82`.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Branch `fix-public-repo-blockers` from `master`. PR creation is a separate step Gary triggers; this plan ends at "all tasks committed on branch, suite green".

**Goal:** The four commands a visitor types first (`instinct --help`, `instinct run`, `instinct run .`, `instinct version`) work as the README describes.

**Architecture:** Four independent, surgical fixes. One dependency bump (typer), two one-line CLI changes, one three-line glob-matching fix in the pipeline. No metric, storage, or design-doc changes — those review findings are out of scope here.

**Tech Stack:** Python 3.12, uv, typer CLI, pytest with `typer.testing.CliRunner`, ruff, mypy (strict on `core/` and `storage/` only).

**Spec:** none — bug-fix plan; the review report above is the requirements source.

## Global Constraints

- Python `>=3.12` (`.python-version` is `3.12`); no `PurePath.full_match` (3.13+).
- `uv` is the only Python workflow tool. Never bare `pip`.
- `uv run pytest` runs with coverage on by default (`addopts` in pyproject). 461 tests pass on master today; each task adds tests and must leave the suite green.
- `uv run ruff check .` must pass (CI runs it before pytest).
- CliRunner merges stderr into stdout (see `tests/test_cli_init.py:62`). New tests assert on `result.stdout` only, never `result.stderr`.
- Commit style: `fix(cli): …`, `fix(pipeline): …`, `chore(deps): …`; imperative, no "I". End every commit message with the session's `Co-Authored-By` and `Claude-Session` trailers.
- Do not edit README.md (its `uv run instinct run` becomes correct after Task 2), the design docs, any metric implementation, or anything under `storage/`.

---

## Scope Decisions (locked)

1. **Bump typer, do not pin click.** `"typer>=0.16,<1"` resolves typer 0.27.2, which no longer depends on the click package at all. Spike on 2026-09-03: all 461 tests pass, ruff passes, both `--help` forms render. Pinning `click<8.2` would only defer the break to the next resolve.
2. **`run` defaults PATH to `.`** rather than making the README pass an argument. The README's `uv run instinct run` is the intended UX.
3. **Glob fix is explicit, not a regex engine.** A leading `**/` in a pattern also matches at the root. Nothing else about matching changes. Observation-identity issues from path spelling (review §4, storage bug 5) are a separate finding and stay out of scope.
4. **`version` reads `METRICS_REGISTRY` lazily inside the command**, matching how `run_cmd` already imports from `savviety_instinct.analyze`. The module-level `REGISTERED_METRIC_VERSIONS` placeholder is deleted; nothing else references it.
5. **Validation gate skipped.** Each fix is under 20 lines and was reproduced and probed in the review session.

---

## File Structure

| Path | Purpose |
|------|---------|
| `pyproject.toml` | typer constraint `>=0.12,<0.13` → `>=0.16,<1` |
| `uv.lock` | Re-resolved; committed with pyproject in Task 1 |
| `src/savviety_instinct/cli/app.py` | Task 2: `run` PATH default. Task 4: `version` lists registry metrics; delete placeholder dict; fix module docstring |
| `src/savviety_instinct/analyze/pipeline.py` | Task 3: `_is_suppressed` handles leading `**/` at root |
| `tests/test_cli_help.py` | New: `--help` on root and on `run` |
| `tests/test_cli_run.py` | Task 2: bare `run`; Task 3: `run .` skips `.venv` under default suppressions |
| `tests/test_analyze_pipeline.py` | Task 3: unit tests for `_is_suppressed` |
| `tests/test_cli_version.py` | Task 4: every registry metric appears with its version |

---

### Task 0: Branch

- [ ] **Step 1: Create the branch from a clean master**

```bash
git status --short          # must be empty
git checkout master && git pull --ff-only
git checkout -b fix-public-repo-blockers
```

---

### Task 1: `instinct --help` crashes (typer/click incompatibility)

**Files:**
- Modify: `pyproject.toml:8` (`"typer>=0.12,<0.13"`)
- Modify: `uv.lock` (regenerated)
- Create: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: `savviety_instinct.cli.app.app` (Typer app object).
- Produces: nothing new. Later tasks rely on typer ≥0.16 semantics: a `typer.Argument` with a default is optional; `CliRunner.invoke(...).stdout` contains merged output.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_help.py`:

```python
"""`--help` must render on the root app and on `run`.

Regression: typer 0.12.5 with click 8.3.2 raised
`TypeError: Parameter.make_metavar() missing 1 required positional argument: 'ctx'`
on every --help invocation. No earlier test exercised --help.
"""

from __future__ import annotations

from typer.testing import CliRunner

from savviety_instinct.cli.app import app

runner = CliRunner()


def test_root_help_renders_and_lists_commands() -> None:
    result = runner.invoke(app, ["--help"], catch_exceptions=False)
    assert result.exit_code == 0
    for cmd in ("version", "init", "run"):
        assert cmd in result.stdout


def test_run_help_renders() -> None:
    result = runner.invoke(app, ["run", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "--help" in result.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli_help.py -v --no-cov`
Expected: both FAIL with `TypeError: Parameter.make_metavar() missing 1 required positional argument: 'ctx'`.

- [ ] **Step 3: Bump the typer constraint and re-lock**

In `pyproject.toml`, change the dependency line:

```toml
    "typer>=0.16,<1",
```

Then:

```bash
uv lock
uv sync
uv run python -c "import typer; print(typer.__version__)"   # expect 0.27.x or later
```

- [ ] **Step 4: Run the tests to verify they pass, then the literal commands**

Run: `uv run pytest tests/test_cli_help.py -v --no-cov`
Expected: 2 PASS.

Run: `uv run instinct --help && uv run instinct run --help`
Expected: both print a usage panel, exit 0, no traceback.

- [ ] **Step 5: Full suite and lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 463 passed; "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/test_cli_help.py
git commit -m "chore(deps): bump typer to >=0.16 so --help renders

typer 0.12.5 is incompatible with the click 8.3.2 the lockfile resolved;
every --help invocation raised TypeError. typer 0.27 drops the click
dependency entirely. Adds the first tests that exercise --help."
```

(Append the session trailers.)

---

### Task 2: bare `instinct run` crashes

**Files:**
- Modify: `src/savviety_instinct/cli/app.py:94-99` (the `run_cmd` signature)
- Test: `tests/test_cli_run.py`

**Interfaces:**
- Consumes: `expected_row_count(n_functions, n_modules)` from `tests/_helpers.py`; `_write_config(cfg_dir)` already in `tests/test_cli_run.py`.
- Produces: `run` accepts zero arguments and analyzes the current directory.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_run.py`:

```python
def test_run_without_path_analyzes_current_directory(tmp_path, monkeypatch) -> None:
    """README documents `uv run instinct run` with no argument (README.md:52)."""
    _write_config(tmp_path / ".instinct")
    shutil.copy(FIXTURES / "metric_fixtures.py", tmp_path / "metric_fixtures.py")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run"], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    assert len(rows) == expected_row_count(n_functions=10, n_modules=1)
```

Add `import shutil` to the imports at the top of the file (stdlib imports go first; ruff `I` rule enforces order).

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli_run.py::test_run_without_path_analyzes_current_directory -v --no-cov`
Expected: FAIL. With typer ≥0.16 a required argument that is omitted produces exit code 2 and a "Missing argument 'PATH'" usage error, so the `exit_code == 0` assertion fails. (On typer 0.12 the same call crashed with `AttributeError: 'NoneType' object has no attribute 'exists'`.)

- [ ] **Step 3: Default PATH to the current directory**

In `src/savviety_instinct/cli/app.py`, replace the `run_cmd` signature:

```python
@app.command("run")
def run_cmd(
    path: Path = typer.Argument(  # noqa: B008
        Path("."),
        help="File or directory to analyze (default: current directory). "
        "Must be a .py file or a dir with .py files.",
    ),
) -> None:
```

Leave the existing `if not path.exists():` guard at the top of the body unchanged.

- [ ] **Step 4: Run the test to verify it passes, then the literal command**

Run: `uv run pytest tests/test_cli_run.py -v --no-cov`
Expected: all PASS (4 tests).

Run, from a scratch directory that has `.instinct/config.yaml` containing `scope: personal` and one `.py` file:

```bash
uv run --project /home/gary/repos/instinct instinct run
```

Expected: metric rows on stdout, `[summary] …` on stderr, exit 0.

- [ ] **Step 5: Full suite and lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 464 passed; clean.

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/cli/app.py tests/test_cli_run.py
git commit -m "fix(cli): default run PATH to the current directory

Bare \`instinct run\`, the form the README documents, crashed with
AttributeError because PATH was required and typer 0.12 passed None."
```

(Append the session trailers.)

---

### Task 3: `instinct run .` walks `.venv` (root-level `**/` never matches)

**Files:**
- Modify: `src/savviety_instinct/analyze/pipeline.py:125-127` (`_is_suppressed`)
- Test: `tests/test_analyze_pipeline.py`
- Test: `tests/test_cli_run.py`

**Interfaces:**
- Consumes: `_is_suppressed(path: Path, patterns: list[str]) -> bool` (private, imported directly by tests, same as `_discover_files` already is).
- Produces: same signature; a pattern beginning with `**/` now also matches when the remainder matches from the path root.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_analyze_pipeline.py`. Change the existing import line `from savviety_instinct.analyze.pipeline import run_pipeline` to `from savviety_instinct.analyze.pipeline import _is_suppressed, run_pipeline`. `pytest` and `Path` are already imported in that file.

```python
@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        # Relative, top-level: these are what `instinct run .` produces.
        (Path(".venv/lib/site.py"), "**/.venv/**", True),
        (Path("test_foo.py"), "**/test_*.py", True),
        (Path("tests/test_foo.py"), "**/tests/**", True),
        # Nested and absolute forms already matched before the fix and must still match.
        (Path("pkg/.venv/x.py"), "**/.venv/**", True),
        (Path("/abs/.venv/x.py"), "**/.venv/**", True),
        # Ordinary source must not be suppressed.
        (Path("src/pkg/mod.py"), "**/.venv/**", False),
        (Path("src/pkg/mod.py"), "**/test_*.py", False),
    ],
)
def test_is_suppressed_matches_leading_doublestar_at_root(
    path: Path, pattern: str, expected: bool
) -> None:
    """fnmatch('**/.venv/**') needs a directory before '.venv'; a relative
    top-level path has none, so the default suppress list was inert for
    `instinct run .` (2026-09-03 review, blocker 3)."""
    assert _is_suppressed(path, [pattern]) is expected
```

- [ ] **Step 2: Write the failing CLI test**

Append to `tests/test_cli_run.py`:

```python
def test_run_dot_skips_venv_under_default_suppressions(tmp_path, monkeypatch) -> None:
    """`instinct run .` on this repo printed 230k rows from .venv/ (2026-09-03 review)."""
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")  # default suppress list
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def real(x):\n    return x + 1\n")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "junk.py").write_text("def junk(y):\n    return y\n")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", "."], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    assert rows, "expected metric rows for pkg/mod.py"
    assert all(".venv/" not in row for row in rows), rows
    assert any("pkg/mod.py" in row for row in rows)
```

- [ ] **Step 3: Run both to verify they fail**

Run: `uv run pytest tests/test_analyze_pipeline.py::test_is_suppressed_matches_leading_doublestar_at_root tests/test_cli_run.py::test_run_dot_skips_venv_under_default_suppressions -v --no-cov`
Expected: the three relative top-level parametrizations FAIL (`assert False is True`); the CLI test FAILS on the `.venv/` assertion. The other four parametrizations PASS.

- [ ] **Step 4: Fix `_is_suppressed`**

In `src/savviety_instinct/analyze/pipeline.py`, replace the function:

```python
def _is_suppressed(path: Path, patterns: list[str]) -> bool:
    # fnmatch treats a leading "**/" as "at least one directory, then /".
    # A relative top-level path such as ".venv/lib/x.py" has no directory
    # before ".venv", so "**/.venv/**" never matched it and `instinct run .`
    # walked the virtualenv. Also try the pattern with "**/" stripped so it
    # matches from the root.
    s = path.as_posix()
    for pat in patterns:
        if fnmatch.fnmatch(s, pat):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(s, pat[3:]):
            return True
    return False
```

- [ ] **Step 5: Run the tests to verify they pass, then the literal command on this repo**

Run: `uv run pytest tests/test_analyze_pipeline.py tests/test_cli_run.py -v --no-cov`
Expected: all PASS, including the pre-existing `test_suppression_skips_files`.

Run, from the repo root (it has `.instinct/config.yaml`):

```bash
uv run instinct run . 2>/dev/null | grep -c '^\.venv/'
uv run instinct run . 2>/dev/null | wc -l
```

Expected: `0`, then a count in the hundreds (888 on master when run as `run src`), not 230k.

- [ ] **Step 6: Full suite and lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 472 passed (464 + 7 parametrized + 1 CLI); clean.

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/analyze/pipeline.py tests/test_analyze_pipeline.py tests/test_cli_run.py
git commit -m "fix(pipeline): honor **/ suppress patterns at the path root

fnmatch requires a directory before the glob remainder, so the default
suppress list never matched relative top-level paths and \`instinct run .\`
walked .venv/. A leading **/ now also matches from the root."
```

(Append the session trailers.)

---

### Task 4: `instinct version` reports no metrics

**Files:**
- Modify: `src/savviety_instinct/cli/app.py:1-15` (module docstring), `:42-56` (placeholder dict and `version_cmd`)
- Test: `tests/test_cli_version.py`

**Interfaces:**
- Consumes: `savviety_instinct.analyze.METRICS_REGISTRY` (tuple of Metric objects with `.id: str` and `.version: str`).
- Produces: `instinct version` output shape:
  ```
  instinct 0.1.0
  metrics:
    cognitive_complexity: 1.2.0
    …
  ```

- [ ] **Step 1: Write the failing test**

Replace `test_version_mentions_metrics_section` in `tests/test_cli_version.py` with:

```python
def test_version_lists_every_registered_metric() -> None:
    result = runner.invoke(app, ["version"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "(none registered)" not in result.stdout
    for metric in METRICS_REGISTRY:
        assert f"  {metric.id}: {metric.version}" in result.stdout
```

Add `from savviety_instinct.analyze import METRICS_REGISTRY` to the imports (keep alphabetical order within the first-party group for ruff `I`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli_version.py -v --no-cov`
Expected: `test_version_lists_every_registered_metric` FAILS on `"(none registered)" not in result.stdout`.

- [ ] **Step 3: Read the registry inside `version_cmd`; delete the placeholder**

In `src/savviety_instinct/cli/app.py`:

Delete these lines entirely (the comment and the dict):

```python
# Slice 1 has no registered metrics. Later slices append to this dict as
# they register their metrics (metric_id -> metric_version).
REGISTERED_METRIC_VERSIONS: dict[str, str] = {}
```

Replace `version_cmd` with:

```python
@app.command("version")
def version_cmd() -> None:
    """Print tool and metric versions."""
    # Lazy import, as in run_cmd: analyze pulls in tree-sitter and the
    # metric modules, which the other commands do not need.
    from savviety_instinct.analyze import METRICS_REGISTRY

    typer.echo(f"instinct {__version__}")
    typer.echo("metrics:")
    for metric in sorted(METRICS_REGISTRY, key=lambda m: m.id):
        typer.echo(f"  {metric.id}: {metric.version}")
```

In the module docstring, change the first surface line so it no longer claims Slice 1 scope:

```python
"""Instinct CLI (Typer).

Commands:
    instinct version   — print tool version and every registered metric version
```

(Keep the remaining docstring lines as they are.)

- [ ] **Step 4: Run the tests to verify they pass, then the literal command**

Run: `uv run pytest tests/test_cli_version.py tests/test_no_network.py -v --no-cov`
Expected: all PASS.

Run: `uv run instinct version`
Expected: `instinct 0.1.0`, `metrics:`, then nine indented `id: version` lines sorted by id, starting with `cognitive_complexity: 1.2.0`.

- [ ] **Step 5: Full suite, lint, and type check**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: 472 passed; ruff clean; mypy reports no new errors (mypy is strict only for `core/` and `storage/`, neither touched here; compare against `git stash; uv run mypy src; git stash pop` if anything is reported).

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/cli/app.py tests/test_cli_version.py
git commit -m "fix(cli): list registered metric versions in version output

REGISTERED_METRIC_VERSIONS was the Slice 1 placeholder and never populated,
so \`instinct version\` reported no metrics while nine were registered.
Read METRICS_REGISTRY directly."
```

(Append the session trailers.)

---

## Acceptance Gate

All four literal commands, run from the repo root on the branch:

```bash
uv run instinct --help                                   # usage panel, exit 0
uv run instinct run --help                               # usage panel, exit 0
uv run instinct run 2>/dev/null | wc -l                  # hundreds of rows, not 230k
uv run instinct run . 2>/dev/null | grep -c '^\.venv/'   # 0
uv run instinct version                                  # nine metric lines
uv run pytest -q && uv run ruff check .                  # 472 passed, clean
git log --oneline master..HEAD                           # exactly 4 commits
```

Not in this plan, tracked in the review report: metric divergences from Sonar (§3), storage identity and tier bugs (§4), README and design-doc claim corrections (§5).
