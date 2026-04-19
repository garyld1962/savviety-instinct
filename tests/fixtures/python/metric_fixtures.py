"""Hand-crafted fixtures with known metric values.

Each function has a comment block documenting its expected
statement_count / cyclomatic / cognitive / max_nesting / npath /
identifier_quality. When the metric formula changes, UPDATE THESE
COMMENTS in lockstep. Values are ground truth — do not adjust them to
match code output; iterate code to match these.
"""


def empty() -> None:
    """statement_count=0, cyclomatic=1, cognitive=0, max_nesting=0, npath=1, identifier_quality=1.0."""


def two_statements(x: int) -> int:
    """statement_count=2, cyclomatic=1, cognitive=0, max_nesting=0, npath=1, identifier_quality=~0.333."""
    y = x + 1
    return y


def single_if(x: int) -> int:
    """statement_count=3, cyclomatic=2 (if), cognitive=1 (if), max_nesting=1, npath=3, identifier_quality=0.5."""
    if x > 0:
        return x
    return 0


def single_if_with_boolean(x: int, y: int) -> int:
    """statement_count=3, cyclomatic=3 (if + bool group), cognitive=2 (if +1, bool group +1), max_nesting=1, npath=4, identifier_quality=~0.333."""
    if x > 0 and y > 0:
        return x + y
    return 0


def nested_if(x: int) -> int:
    """statement_count=4, cyclomatic=3 (two ifs), cognitive=3 (outer if +1, inner if +1+1 nesting=2), max_nesting=2, npath=5, identifier_quality=0.5."""
    if x > 0:  # noqa: SIM102 — intentional nested if; fixture tests nesting depth
        if x < 100:
            return x
    return 0


def for_loop_only(items: list[int]) -> int:
    """statement_count=4, cyclomatic=2 (for), cognitive=1 (for), max_nesting=1, npath=3, identifier_quality=1.0.

    Revised from original estimate of 3: the return statement is a separate
    executable statement, giving total=0(1)+for(1)+total+=item(1)+return(1)=4.
    """
    total = 0
    for item in items:
        total += item
    return total


def for_with_if(items: list[int]) -> int:
    """statement_count=5, cyclomatic=3 (for + if), cognitive=3 (for +1, nested if +1+1 nesting=2), max_nesting=2, npath=5, identifier_quality=1.0.

    Revised from original estimate of 4: total=0(1)+for(1)+if(1)+total+=item(1)+return(1)=5.
    """
    total = 0
    for item in items:
        if item > 0:
            total += item
    return total


def try_except(x: int) -> int:
    """statement_count=4, cyclomatic=2 (except), cognitive=1 (except), max_nesting=1, npath=2, identifier_quality=~0.667."""
    try:
        return 1 // x
    except ZeroDivisionError:
        return 0


def ternary(x: int) -> int:
    """statement_count=1, cyclomatic=2 (ternary), cognitive=1 (ternary), max_nesting=0, npath=3, identifier_quality=0.5."""
    return x if x > 0 else -x


def comprehension(items: list[int]) -> list[int]:
    """statement_count=1, cyclomatic=2 (comprehension), cognitive=1 (comprehension), max_nesting=0, npath=3, identifier_quality=~0.667."""
    return [i for i in items if i > 0]
