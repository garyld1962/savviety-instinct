"""Differential test: cognitive_complexity vs cognitive_complexity PyPI package.

radon does NOT ship a cognitive-complexity implementation (only cyclomatic
and halstead). We use the `cognitive_complexity` PyPI package (v1.3.0,
Rocky Meza) as an independent reference. It parses via Python's stdlib
`ast` module — a completely different parser than our tree-sitter —
so agreement carries real cross-check weight.

Reference philosophy differs from ours on three points:
  1. Comprehensions — reference: not counted. Instinct: +1 per comprehension
     (matches SonarSource's own implementation; reference's choice is a
     package-author decision).
  2. Async constructs — reference: not counted. Instinct: +1 per async
     for/with, same as the sync equivalents (ours appears more correct
     per SonarSource's intent; reference simply ignores async nodes).
  3. `except*` — reference: +1 per clause. Instinct: not counted (Bug B3).
  4. `match` — instinct counts +1 per case arm (Bug B1 fix); reference
     silently ignores `Match` / `match_case` AST nodes. Documented as
     a delta below.

Structure mirrors test_metric_differential_cyclomatic.py:
  - `test_cognitive_matches_reference` — parametrize over agreement cases
  - `test_cognitive_documented_deltas` — pin both values with reason
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from cognitive_complexity.api import get_cognitive_complexity

from savviety_instinct.analyze import COGNITIVE_METRIC
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Language,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "python"


def _reference_by_qname(source: str) -> dict[tuple[str | None, str], int]:
    """Parse via stdlib `ast` and compute cognitive for each function /
    method. Keyed by (classname, name). Nested function definitions are
    enumerated (unlike our parser) — we ignore them for the differential
    to avoid mixing two design choices."""
    out: dict[tuple[str | None, str], int] = {}

    def walk(parent: ast.AST, classname: str | None) -> None:
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[(classname, child.name)] = get_cognitive_complexity(child)
                # do NOT recurse into function bodies — matches our parser's
                # "skip nested functions" design (Slice 2 decision)
            elif isinstance(child, ast.ClassDef):
                walk(child, classname=child.name)

    walk(ast.parse(source), classname=None)
    return out


def _instinct_by_qname(fixture_path: Path) -> dict[tuple[str | None, str], int]:
    result = PYTHON_ADAPTER.parse_path(fixture_path)
    ctx = AnalysisContext(parse_result=result)
    out: dict[tuple[str | None, str], int] = {}
    for fn in result.functions:
        artifact = Artifact(
            ast_hash=fn.ast_hash,
            language=Language.PYTHON,
            kind=ArtifactKind.FUNCTION,
            name=fn.name,
            enclosing_scope=fn.enclosing_class,
            source_range=fn.source_range,
        )
        out[(fn.enclosing_class, fn.name)] = COGNITIVE_METRIC.compute(artifact, ctx).value
    return out


# ---------- Agreement cases ----------

AGREEMENT_CASES: list[tuple[str, str | None, str]] = [
    # metric_fixtures.py (9 of 10 — comprehension diverges)
    ("metric_fixtures.py", None, "empty"),
    ("metric_fixtures.py", None, "two_statements"),
    ("metric_fixtures.py", None, "single_if"),
    ("metric_fixtures.py", None, "single_if_with_boolean"),
    ("metric_fixtures.py", None, "nested_if"),
    ("metric_fixtures.py", None, "for_loop_only"),
    ("metric_fixtures.py", None, "for_with_if"),
    ("metric_fixtures.py", None, "try_except"),
    ("metric_fixtures.py", None, "ternary"),
    # async_generator.py — only `passthrough` agrees (no async iter)
    ("adversarial/async_generator.py", None, "passthrough"),
    # decorator_stack.py — all agree at 0
    ("adversarial/decorator_stack.py", None, "cached_helper"),
    # Thing.name methods excluded due to Bug B2 qualified_name collision
    ("adversarial/decorator_stack.py", "Thing", "from_id"),
    # exception_groups.py
    ("adversarial/exception_groups.py", None, "run_all"),
    # generics_pep695.py
    ("adversarial/generics_pep695.py", None, "identity"),
    ("adversarial/generics_pep695.py", None, "head"),
    ("adversarial/generics_pep695.py", "Container", "__init__"),
    ("adversarial/generics_pep695.py", "Container", "get"),
    # match_statement.py — instinct counts +1 per case (B1 fix); reference
    # ignores match. See DELTA_CASES below.
    # nested_functions.py outer only
    ("adversarial/nested_functions.py", None, "make_counter"),
    ("adversarial/nested_functions.py", None, "make_types"),
    # walrus.py — count_trim has only `if`, agrees
    ("adversarial/walrus.py", None, "count_trim"),
]


@pytest.mark.parametrize(
    "fixture,classname,fname",
    AGREEMENT_CASES,
)
def test_cognitive_matches_reference(fixture: str, classname: str | None, fname: str) -> None:
    path = FIXTURES_ROOT / fixture
    ref_map = _reference_by_qname(path.read_text())
    instinct_map = _instinct_by_qname(path)
    key = (classname, fname)
    assert key in instinct_map, f"instinct didn't extract {fname} from {fixture}"
    assert key in ref_map, f"reference didn't extract {fname} from {fixture}"
    assert instinct_map[key] == ref_map[key], (
        f"{fixture}:{classname or '<module>'}.{fname} diverged — "
        f"instinct={instinct_map[key]} ref={ref_map[key]}"
    )


# ---------- Documented deltas ----------

DELTA_CASES: list[tuple[str, str | None, str, int, int, str]] = [
    (
        "metric_fixtures.py",
        None,
        "comprehension",
        1,
        0,
        "Philosophy split: instinct counts comprehensions (+1); reference package ignores them",
    ),
    (
        "adversarial/async_generator.py",
        None,
        "gen_chunks",
        1,
        0,
        "Philosophy split: instinct counts `async for` (+1); reference ignores async constructs",
    ),
    (
        "adversarial/async_generator.py",
        None,
        "gather",
        1,
        0,
        "Philosophy split: async for / async with ignored by reference",
    ),
    (
        "adversarial/exception_groups.py",
        None,
        "handle_many",
        0,
        2,
        "Bug B3: instinct doesn't count except* clauses; reference correctly does (+1 each)",
    ),
    (
        "adversarial/match_statement.py",
        None,
        "classify_shape",
        3,
        0,
        "B1 fix: instinct counts +1 per case arm (3 arms → 3); cognitive_complexity "
        "package is blind to match",
    ),
    (
        "adversarial/match_statement.py",
        None,
        "unpack_point",
        3,
        0,
        "B1 fix: instinct counts +1 per case arm (3 arms → 3); cognitive_complexity "
        "package is blind to match",
    ),
    (
        "adversarial/multi_clause_comp.py",
        None,
        "pairs",
        1,
        0,
        "Philosophy split: comprehension counting",
    ),
    (
        "adversarial/multi_clause_comp.py",
        None,
        "nested_dict",
        1,
        0,
        "Philosophy split: comprehension counting",
    ),
    (
        "adversarial/walrus.py",
        None,
        "find_matching",
        1,
        0,
        "Philosophy split: comprehension in return statement",
    ),
]


@pytest.mark.parametrize(
    "fixture,classname,fname,expected_instinct,expected_reference,reason",
    DELTA_CASES,
)
def test_cognitive_documented_deltas(
    fixture: str,
    classname: str | None,
    fname: str,
    expected_instinct: int,
    expected_reference: int,
    reason: str,
) -> None:
    """Locks documented instinct-vs-reference divergences. Most deltas here
    are philosophy differences (comprehension / async counting) — the
    reference's choice differs from SonarSource's Sonar implementation,
    which is the spec our metric targets. Bug B3 (except*) is the one
    genuine correctness gap on our side."""
    path = FIXTURES_ROOT / fixture
    ref_map = _reference_by_qname(path.read_text())
    instinct_map = _instinct_by_qname(path)
    key = (classname, fname)
    assert instinct_map[key] == expected_instinct, (
        f"instinct drifted at {fixture}:{fname} — "
        f"expected {expected_instinct}, got {instinct_map[key]}. "
        f"Delta reason: {reason}"
    )
    assert ref_map[key] == expected_reference, (
        f"reference drifted at {fixture}:{fname} — "
        f"expected {expected_reference}, got {ref_map[key]}. "
        f"Delta reason: {reason}"
    )
