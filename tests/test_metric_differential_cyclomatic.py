"""Differential test: cyclomatic_complexity vs radon.

radon is an established Python complexity tool. Cross-checking our metric
against radon's `cc_visit()` as independent ground truth catches
confirmation-bias drift — where the metric author picks expected values
from the same mental model that wrote the code.

Two test functions:

1. `test_cyclomatic_matches_radon` — exact-match parametrize over the
   cases where both tools agree. Regressions here mean one side's
   semantics shifted.

2. `test_cyclomatic_documented_deltas` — pins both sides' values for the
   small set of cases where we deliberately diverge. Two reasons apply:
     - Known Gap #2 in cyclomatic.py: comprehensions counted +1 per
       group; radon counts +1 per for/if clause.
     - Bug B1 fix (parse-bugs branch): we now count every case_clause
       as +1; radon skips a trailing bare `case _:` as the default arm.
       For fixtures without a trailing wildcard the values agree.

Decorator-stack getter/setter methods are excluded because the differential
test keys by (class, name); B2's fix gives our qualified_name unique
suffixes but the radon side has no equivalent disambiguator, so the
two methods would still collide in the lookup dict. Out of scope here.

Exception groups (`except*`): instinct counts each clause +1 (Bug B3
fix); radon is still blind to PEP 654 — moved to documented deltas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from radon.complexity import cc_visit

from savviety_instinct.analyze import CYCLOMATIC_METRIC
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Language,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES_ROOT = Path(__file__).parent / "fixtures" / "python"


def _radon_by_qname(source: str) -> dict[tuple[str | None, str], int]:
    """Map (classname, name) -> complexity for every Function radon finds.

    radon emits methods both inside the parent Class record AND flat at
    the top level with `classname` populated — we read the flat entries.
    """
    out: dict[tuple[str | None, str], int] = {}
    for v in cc_visit(source):
        if type(v).__name__ == "Function":
            out[(v.classname, v.name)] = v.complexity
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
        out[(fn.enclosing_class, fn.name)] = CYCLOMATIC_METRIC.compute(artifact, ctx).value
    return out


# ---------- Agreement: instinct and radon produce identical values ----------

AGREEMENT_CASES: list[tuple[str, str | None, str]] = [
    # metric_fixtures.py (Slice 3/4a ground-truth fixtures)
    ("metric_fixtures.py", None, "empty"),
    ("metric_fixtures.py", None, "two_statements"),
    ("metric_fixtures.py", None, "single_if"),
    ("metric_fixtures.py", None, "single_if_with_boolean"),
    ("metric_fixtures.py", None, "nested_if"),
    ("metric_fixtures.py", None, "for_loop_only"),
    ("metric_fixtures.py", None, "for_with_if"),
    ("metric_fixtures.py", None, "try_except"),
    ("metric_fixtures.py", None, "ternary"),
    # adversarial/async_generator.py
    ("adversarial/async_generator.py", None, "gen_chunks"),
    ("adversarial/async_generator.py", None, "gather"),
    ("adversarial/async_generator.py", None, "passthrough"),
    # adversarial/decorator_stack.py — module-scope function only
    # (methods excluded due to Bug B2 qualified_name collision)
    ("adversarial/decorator_stack.py", None, "cached_helper"),
    # adversarial/exception_groups.py — run_all has no except*, agrees.
    # handle_many is a documented delta below (B3 fix vs radon blind spot).
    ("adversarial/exception_groups.py", None, "run_all"),
    # adversarial/match_statement.py — unpack_point has 3 non-wildcard cases;
    # classify_shape ends in bare `case _:` so radon discounts it (delta below).
    ("adversarial/match_statement.py", None, "unpack_point"),
    # adversarial/generics_pep695.py
    ("adversarial/generics_pep695.py", None, "identity"),
    ("adversarial/generics_pep695.py", None, "head"),
    ("adversarial/generics_pep695.py", "Container", "__init__"),
    ("adversarial/generics_pep695.py", "Container", "get"),
    # adversarial/nested_functions.py — outer functions only
    ("adversarial/nested_functions.py", None, "make_counter"),
    ("adversarial/nested_functions.py", None, "make_types"),
    # adversarial/walrus.py — count_trim has `if` only, no comprehension; agrees
    ("adversarial/walrus.py", None, "count_trim"),
]


@pytest.mark.parametrize(
    "fixture,classname,fname",
    AGREEMENT_CASES,
    ids=lambda p: p if p is not None else "module",
)
def test_cyclomatic_matches_radon(fixture: str, classname: str | None, fname: str) -> None:
    path = FIXTURES_ROOT / fixture
    radon_map = _radon_by_qname(path.read_text())
    instinct_map = _instinct_by_qname(path)
    key = (classname, fname)
    assert key in instinct_map, f"instinct didn't extract {fname} from {fixture}"
    assert key in radon_map, f"radon didn't extract {fname} from {fixture}"
    assert instinct_map[key] == radon_map[key], (
        f"{fixture}:{classname or '<module>'}.{fname} diverged — "
        f"instinct={instinct_map[key]} radon={radon_map[key]}"
    )


# ---------- Documented deltas: pinned both sides ----------

# Each case locks BOTH our value and radon's value. Drift on either
# side flags the divergence for re-evaluation.
DELTA_CASES: list[tuple[str, str | None, str, int, int, str]] = [
    (
        "metric_fixtures.py",
        None,
        "comprehension",
        2,
        3,
        "Known Gap #2: comprehension counted +1 per group; radon counts +1 per for/if clause",
    ),
    (
        "adversarial/match_statement.py",
        None,
        "classify_shape",
        4,
        3,
        "B1 fix: instinct counts every case_clause +1 (3 arms → 4); radon "
        "skips the trailing bare `case _:` as the default arm",
    ),
    (
        "adversarial/exception_groups.py",
        None,
        "handle_many",
        3,
        1,
        "B3 fix: instinct counts each except* clause +1 (2 arms → 3); "
        "radon is blind to PEP 654 except_group_clause",
    ),
    (
        "adversarial/multi_clause_comp.py",
        None,
        "pairs",
        2,
        5,
        "Known Gap #2: multi-clause comprehension (2× for + 2× if)",
    ),
    (
        "adversarial/multi_clause_comp.py",
        None,
        "nested_dict",
        2,
        6,
        "Known Gap #2: nested comprehension + dict comprehension + clauses",
    ),
    (
        "adversarial/walrus.py",
        None,
        "find_matching",
        2,
        3,
        "Known Gap #2: comprehension with if clause",
    ),
]


@pytest.mark.parametrize(
    "fixture,classname,fname,expected_instinct,expected_radon,reason",
    DELTA_CASES,
)
def test_cyclomatic_documented_deltas(
    fixture: str,
    classname: str | None,
    fname: str,
    expected_instinct: int,
    expected_radon: int,
    reason: str,
) -> None:
    """Locks documented instinct-vs-radon divergences. Drift on either
    side surfaces the fact that something changed — either a fix, a
    regression, or an upstream radon update."""
    path = FIXTURES_ROOT / fixture
    radon_map = _radon_by_qname(path.read_text())
    instinct_map = _instinct_by_qname(path)
    key = (classname, fname)
    assert instinct_map[key] == expected_instinct, (
        f"instinct drifted at {fixture}:{fname} — "
        f"expected {expected_instinct}, got {instinct_map[key]}. "
        f"Delta reason: {reason}"
    )
    assert radon_map[key] == expected_radon, (
        f"radon drifted at {fixture}:{fname} — "
        f"expected {expected_radon}, got {radon_map[key]}. "
        f"Delta reason: {reason}"
    )
