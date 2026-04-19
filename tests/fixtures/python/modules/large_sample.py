"""32 functions with varied shapes. HIGH-confidence tier for all three metrics.

Expected module metrics:
  trivial_delegation_ratio = 6/32 = 0.1875, confidence=MEDIUM (n=32 >= 20)
  median_function_length = 1.0, confidence=HIGH (n=32 >= 10)
  function_length_bimodality = 0.7846, confidence=HIGH (n=32 >= 30)

Delegates (return_passthrough): f01, f03, f04, f08, f16, f31 — 6 total.
The intent is a broadly-distributed sample (many 1-stmt list-comps/builtins); heavily
skewed toward 1 which yields high BC despite not being bimodal in the visual sense.
Statement-count list (sorted): [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 4, 4, 5, 5, 6, 8]
"""
from __future__ import annotations


def f01(xs):
    return sum(xs)


def f02(xs):
    total = 0
    for x in xs:
        total = total + x
    return total


def f03(xs):
    return max(xs)


def f04(xs):
    return min(xs)


def f05(xs):
    total = 0
    count = 0
    for x in xs:
        total = total + x
        count = count + 1
    return total / count if count else 0


def f06(xs):
    return [x for x in xs if x > 0]


def f07(xs, ys):
    return [(x, y) for x in xs for y in ys]


def f08(xs):
    return sorted(xs)


def f09(xs):
    return sorted(xs, reverse=True)


def f10(xs):
    s = set(xs)
    return sorted(s)


def f11(xs):
    total = 0
    for x in xs:
        if x > 0:
            total = total + x
    return total


def f12(xs):
    total = 0
    for x in xs:
        if x < 0:
            total = total + x
    return total


def f13(xs):
    return xs[0] if xs else None


def f14(xs):
    return xs[-1] if xs else None


def f15(xs):
    mid = len(xs) // 2
    return xs[mid] if xs else None


def f16(xs):
    return len(xs)


def f17(xs):
    return sum(xs) / len(xs) if xs else 0


def f18(xs):
    return sum(x * x for x in xs)


def f19(xs):
    return [x + 1 for x in xs]


def f20(xs):
    return [x - 1 for x in xs]


def f21(xs):
    return [x * 2 for x in xs]


def f22(xs):
    return [x // 2 for x in xs]


def f23(xs):
    total = 0
    count = 0
    squared = 0
    for x in xs:
        total = total + x
        squared = squared + x * x
        count = count + 1
    return (total, squared, count)


def f24(xs):
    return {x for x in xs}


def f25(xs):
    return {x: x * 2 for x in xs}


def f26(xs):
    return all(x > 0 for x in xs)


def f27(xs):
    return any(x > 0 for x in xs)


def f28(xs):
    return [x for x in xs if x % 2 == 0]


def f29(xs):
    return [x for x in xs if x % 2 == 1]


def f30(xs):
    xs_sorted = sorted(xs)
    if not xs_sorted:
        return None
    return xs_sorted[len(xs_sorted) // 2]


def f31(xs):
    return reversed(xs)


def f32(xs):
    return list(zip(xs, xs[1:]))
