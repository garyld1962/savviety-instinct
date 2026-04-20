"""Five functions, zero trivial delegates, varied lengths.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = 0.0 (0/5), confidence=LOW (n=5 < 20)
  median_function_length = 10, confidence=LOW (n=5 < 10)
  function_length_bimodality = 0.1678, confidence=LOW (4 <= n=5 < 30)

Functions (source order): three_statements=4/none, seven_statements=7/none,
  ten_statements=10/none, fifteen_statements=15/none, twenty_statements=18/none.
Note: function names are aspirational; actual parser counts differ (twenty_statements=18, not 20).
Statement-count list (sorted): [4, 7, 10, 15, 18]
"""
from __future__ import annotations


def three_statements(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def seven_statements(xs):
    total = 0
    count = 0
    for item in xs:
        total = total + item
        count = count + 1
    average = total / count if count else 0
    return average


def ten_statements(xs, ys):
    total_x = 0
    total_y = 0
    count = 0
    for x in xs:
        total_x = total_x + x
        count = count + 1
    for y in ys:
        total_y = total_y + y
    diff = total_x - total_y
    return diff


def fifteen_statements(xs):
    total = 0
    squared = 0
    cubed = 0
    count = 0
    for item in xs:
        total = total + item
        squared = squared + item * item
        cubed = cubed + item * item * item
        count = count + 1
    if count == 0:
        return (0, 0, 0)
    avg = total / count
    sq_avg = squared / count
    cu_avg = cubed / count
    return (avg, sq_avg, cu_avg)


def twenty_statements(xs, ys, zs):
    totals = [0, 0, 0]
    counts = [0, 0, 0]
    for item in xs:
        totals[0] = totals[0] + item
        counts[0] = counts[0] + 1
    for item in ys:
        totals[1] = totals[1] + item
        counts[1] = counts[1] + 1
    for item in zs:
        totals[2] = totals[2] + item
        counts[2] = counts[2] + 1
    if counts[0] > 0:
        totals[0] = totals[0] / counts[0]
    if counts[1] > 0:
        totals[1] = totals[1] / counts[1]
    if counts[2] > 0:
        totals[2] = totals[2] / counts[2]
    return totals
