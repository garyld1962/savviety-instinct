"""Adversarial fixture: PEP 695 type parameter syntax (Python 3.12+).

`def f[T](x: T) -> T` and `class Container[T]` use the new generics syntax.
Tree-sitter-python 0.23.x supports `type_parameter` nodes; the parser must
not break on them.

Expected:
  functions: 4 (identity, head, __init__, get)
  classes: 1 (Container)
  identity has parameter_names = ("x",); head has ("xs",);
    get has ("self",); __init__ has ("self", "value")
  all delegation_kind: NONE (return x, return xs[0], etc. — no call passthrough)
"""
from __future__ import annotations


def identity[T](x: T) -> T:
    return x


def head[T](xs: list[T]) -> T:
    return xs[0]


class Container[T]:
    def __init__(self, value: T) -> None:
        self._value = value

    def get(self) -> T:
        return self._value
