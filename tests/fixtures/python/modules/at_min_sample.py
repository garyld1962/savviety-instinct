"""Exactly 20 functions: 10 trivial delegates + 9 real-work + 1 helper.

Boundary fixture for MIN_SAMPLE_SIZE=20 in trivial_delegation_ratio — pins
the strict-comparison contract (`n < MIN_SAMPLE_SIZE`). A mutation to
`n <= MIN_SAMPLE_SIZE` would downgrade this module from MEDIUM to LOW, so
the accompanying test fails loudly. See `at_threshold.py` (n=21) for the
comfortable-margin MEDIUM case.

Expected module metrics:
  trivial_delegation_ratio = 10/20 = 0.5, confidence=MEDIUM (n=20 ≥ 20)
  median_function_length = 1, confidence=HIGH (n=20 ≥ 10)
  function_length_bimodality computed over [1]*11 + [4]*9 (see w/d mix below)
"""
from __future__ import annotations


# 10 trivial delegates (RETURN_PASSTHROUGH via `return helper_fn(a)`)
def d01(a): return helper_fn(a)  # noqa: E704
def d02(a): return helper_fn(a)  # noqa: E704
def d03(a): return helper_fn(a)  # noqa: E704
def d04(a): return helper_fn(a)  # noqa: E704
def d05(a): return helper_fn(a)  # noqa: E704
def d06(a): return helper_fn(a)  # noqa: E704
def d07(a): return helper_fn(a)  # noqa: E704
def d08(a): return helper_fn(a)  # noqa: E704
def d09(a): return helper_fn(a)  # noqa: E704
def d10(a): return helper_fn(a)  # noqa: E704


# 9 real-work functions
def w01(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w02(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w03(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w04(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w05(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w06(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w07(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w08(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w09(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


# Helper — NONE classification (return a is not a call)
def helper_fn(a):
    return a
