"""Zero functions. Edge case for empty-module sentinel in all three metrics.

Expected module metrics:
  trivial_delegation_ratio: value=0.0, confidence=LOW, notes="no functions in module"
  median_function_length: value=0, confidence=LOW, notes="no functions in module"
  function_length_bimodality: value=0.0, confidence=LOW, notes="n=0 below minimum 4 for bimodality"
"""
from __future__ import annotations
