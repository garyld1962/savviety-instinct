"""One function, 6 statements, NONE delegation. Sub-threshold for all three metrics.

Expected module metrics:
  trivial_delegation_ratio = 0.0 (0/1), confidence=LOW (n=1 < 20)
  median_function_length = 6, confidence=LOW (n=1 < 10)
  function_length_bimodality = 0.0, confidence=LOW, notes="n=1 below minimum 4 for bimodality"

Statement-count list: [6]
"""
from __future__ import annotations


def only_function(xs):
    total = 0
    count = 0
    for item in xs:
        total = total + item
        count = count + 1
    return total / count if count else 0
