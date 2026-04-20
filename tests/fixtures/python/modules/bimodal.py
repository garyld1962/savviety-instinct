"""Eight functions: 5x 2-statement short + 3x 30-statement long; strong bimodal shape.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = 0.0 (0/8), confidence=LOW (n=8 < 20)
  median_function_length = 2.0, confidence=LOW (n=8 < 10)
  function_length_bimodality = 0.4107, confidence=LOW (4 <= n=8 < 30)

Note: BC=0.4107 reflects the small-n correction in Sarle's formula. The bimodal shape
(5 shorts at 2 + 3 longs at 30) is clearly bimodal visually; BC < 0.555 threshold
due to n=8 penalty. short_1 uses xs[0] (subscript, not call) to avoid assign_delegate.
Statement-count list (sorted): [2, 2, 2, 2, 2, 30, 30, 30]
"""
from __future__ import annotations


def short_1(xs):
    total = xs[0]
    return total


def short_2(xs):
    total = xs[0]
    return total + 1


def short_3(xs):
    total = xs[0]
    return total - 1


def short_4(xs):
    total = xs[0]
    return total * 2


def short_5(xs):
    total = xs[0]
    return total // 2


# Three "long" functions each ~30 statements (simple accumulator padding).
# Exact statement count per function should be verified via REPL; the bimodal
# shape (5 short + 3 long) is what drives the BC > 0.555 expectation.

def long_1(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    f = 0
    g = 0
    h = 0
    i_ = 0
    j = 0
    k = 0
    l = 0
    m = 0
    n = 0
    o = 0
    p = 0
    q = 0
    r = 0
    s = 0
    t = 0
    u = 0
    v = 0
    w = 0
    x_ = 0
    y = 0
    z = 0
    aa = 0
    bb = 0
    cc = 0
    return (a, b, c, d, e, f, g, h, i_, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x_, y, z, aa, bb, cc)


def long_2(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    f = 0
    g = 0
    h = 0
    i_ = 0
    j = 0
    k = 0
    l = 0
    m = 0
    n = 0
    o = 0
    p = 0
    q = 0
    r = 0
    s = 0
    t = 0
    u = 0
    v = 0
    w = 0
    x_ = 0
    y = 0
    z = 0
    aa = 0
    bb = 0
    cc = 0
    return (a, b, c, d, e, f, g, h, i_, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x_, y, z, aa, bb, cc)


def long_3(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    f = 0
    g = 0
    h = 0
    i_ = 0
    j = 0
    k = 0
    l = 0
    m = 0
    n = 0
    o = 0
    p = 0
    q = 0
    r = 0
    s = 0
    t = 0
    u = 0
    v = 0
    w = 0
    x_ = 0
    y = 0
    z = 0
    aa = 0
    bb = 0
    cc = 0
    return (a, b, c, d, e, f, g, h, i_, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x_, y, z, aa, bb, cc)
