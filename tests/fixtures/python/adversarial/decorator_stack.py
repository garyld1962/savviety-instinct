"""Adversarial fixture: stacked decorators, @property / @setter.

Stacked function decorators (@cache + @staticmethod at module scope,
@classmethod + @lru_cache on a method), plus a property/setter pair
that both carry the name `name`.

Bug B2 (fixed in parse-bugs branch):
  Originally `@property` getter and `@<name>.setter` both produced
  qualified_name "Thing.name", collapsing the two for any consumer
  keyed by qualified_name. The fix detects the property-family
  decorator and appends "[getter]" / "[setter]" / "[deleter]" to
  qualified_name. Other duplicates fall back to "@L<line>".

Expected (post-fix):
  functions: 4 — cached_helper, Thing.name[getter], Thing.name[setter], Thing.from_id
  classes: 1 (Thing)
  distinct qualified_names: 4
  all delegation_kind: NONE (no pure passthroughs)
"""
from __future__ import annotations

from functools import cache, lru_cache


@cache
@staticmethod
def cached_helper(x):
    return x * 2


class Thing:
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @classmethod
    @lru_cache(maxsize=32)
    def from_id(cls, ident):
        return cls(ident)
