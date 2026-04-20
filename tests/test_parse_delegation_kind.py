"""Parse-layer detection of FunctionDefNode.delegation_kind (Slice 4b)."""

from __future__ import annotations

from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import DelegationKind


def _fn_kind(source: str, fn_name: str = "f") -> DelegationKind:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<test>")
    assert result.ok, result.errors
    for fn in result.functions:
        if fn.name == fn_name:
            return fn.delegation_kind
    raise LookupError(fn_name)


# ---------- RETURN_PASSTHROUGH ----------


def test_return_passthrough_positional() -> None:
    src = """
def f(a, b):
    return g(a, b)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_keyword_matching_names() -> None:
    src = """
def f(a, b):
    return g(a=a, b=b)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_prefix_of_params() -> None:
    """Calling g(a) from f(a, b) — uses a prefix, still passthrough."""
    src = """
def f(a, b):
    return g(a)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_with_docstring() -> None:
    src = '''
def f(a, b):
    """docstring."""
    return g(a, b)
'''
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_zero_args() -> None:
    src = """
def f():
    return g()
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


# ---------- ASSIGN_DELEGATE ----------


def test_assign_delegate() -> None:
    src = """
def f(a, b):
    x = g(a, b)
    return x
"""
    assert _fn_kind(src) == DelegationKind.ASSIGN_DELEGATE


def test_assign_delegate_with_docstring() -> None:
    src = '''
def f(a):
    """doc."""
    x = g(a)
    return x
'''
    assert _fn_kind(src) == DelegationKind.ASSIGN_DELEGATE


# ---------- WRAPPER_NO_TRANSFORM ----------


def test_wrapper_no_transform() -> None:
    src = """
def f(a, b):
    g(a, b)
"""
    assert _fn_kind(src) == DelegationKind.WRAPPER_NO_TRANSFORM


# ---------- NONE: transformations ----------


def test_none_if_body_has_arithmetic_on_call_result() -> None:
    src = """
def f(a):
    return g(a) + 1
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_call_has_literal_arg() -> None:
    src = """
def f(a):
    return g(a, 1)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_call_has_wrong_arg_order() -> None:
    src = """
def f(a, b):
    return g(b, a)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_keyword_name_mismatches_value() -> None:
    src = """
def f(a, b):
    return g(a=b)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_body_has_control_flow() -> None:
    src = """
def f(a):
    if a:
        return g(a)
    return None
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_pass_only_body() -> None:
    src = """
def f():
    pass
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_ellipsis_only_body() -> None:
    src = """
def f():
    ...
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_return_literal() -> None:
    src = """
def f():
    return 42
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_self_attribute_assignment() -> None:
    """`self.x = x` is data initialization, not delegation."""
    src = """
class C:
    def __init__(self, x):
        self.x = x
"""
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    init = next(fn for fn in result.functions if fn.name == "__init__")
    assert init.delegation_kind == DelegationKind.NONE


def test_none_for_super_method_delegation() -> None:
    """super().foo(a) — attribute-call, KNOWN GAP #1; classified NONE."""
    src = """
class C:
    def foo(self, a):
        return super().foo(a)
"""
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    foo = next(fn for fn in result.functions if fn.name == "foo")
    assert foo.delegation_kind == DelegationKind.NONE


def test_none_for_async_passthrough() -> None:
    """async def g(): return await f(a) — KNOWN GAP #4; classified NONE."""
    src = """
async def f(a):
    return await g(a)
"""
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    async_f = next(fn for fn in result.functions if fn.name == "f")
    assert async_f.delegation_kind == DelegationKind.NONE


def test_none_for_attribute_call_target() -> None:
    """`return self.helper(a)` — attribute target, not identifier."""
    src = """
class C:
    def foo(self, a):
        return self.helper(a)
"""
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    foo = next(fn for fn in result.functions if fn.name == "foo")
    assert foo.delegation_kind == DelegationKind.NONE


def test_none_for_splat_args() -> None:
    src = """
def f(*args):
    return g(*args)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_three_statement_body() -> None:
    src = """
def f(a):
    x = g(a)
    y = x + 1
    return y
"""
    assert _fn_kind(src) == DelegationKind.NONE


# ---------- Default arg injection (documented as passthrough) ----------


def test_default_arg_injection_is_passthrough() -> None:
    """def f(a, b=5): return g(a, b) — body passes params through; signature
    default not considered transformation. Documented decision."""
    src = """
def f(a, b=5):
    return g(a, b)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH
