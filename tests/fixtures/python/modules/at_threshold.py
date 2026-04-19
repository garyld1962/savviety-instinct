"""Exactly 21 functions: 10 trivial delegates + 10 real-work + 1 helper.
At MEDIUM-confidence threshold for trivial_delegation_ratio (n>=20).

Expected module metrics:
  trivial_delegation_ratio = 10/21 ≈ 0.4762, confidence=MEDIUM (n=21 >= 20)
  median_function_length = 1, confidence=HIGH (n=21 >= 10)
  function_length_bimodality = 0.7077, confidence=LOW (n=21 < 30)

Note: the helper function `h` (return a) is NOT a trivial delegate (a is not a call).
So 10 trivial out of 21 total. w01-w10 are also none (real loops, not call-passthrough).
Parser order (reverse source): h=1/none, w10..w01=4/none each, d10..d01=1/return_passthrough each.
Sorted counts: [1 x11 (h + d01-d10), 4 x10 (w01-w10)]
Median is 1 (11th of 21 values in sorted order = first value > all 11 ones = still a 1).
Statement-count list (sorted): [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4]
"""
from __future__ import annotations


# 10 trivial delegates (RETURN_PASSTHROUGH via `return h(a)`)
def d01(a): return h(a)  # noqa: E704
def d02(a): return h(a)  # noqa: E704
def d03(a): return h(a)  # noqa: E704
def d04(a): return h(a)  # noqa: E704
def d05(a): return h(a)  # noqa: E704
def d06(a): return h(a)  # noqa: E704
def d07(a): return h(a)  # noqa: E704
def d08(a): return h(a)  # noqa: E704
def d09(a): return h(a)  # noqa: E704
def d10(a): return h(a)  # noqa: E704


# 10 real-work functions
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


def w10(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


# Helper — NONE classification (return a is not a call)
def h(a):
    return a
