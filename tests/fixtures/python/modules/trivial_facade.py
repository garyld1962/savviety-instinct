"""Six user-visible functions; five are trivial delegates covering all three DelegationKinds. Plus helper — 7 total.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = 5/7 ≈ 0.7143, confidence=LOW (n=7 < 20)
  median_function_length = 1, confidence=LOW (n=7 < 10)
  function_length_bimodality = 0.5027, confidence=LOW (4 <= n=7 < 30)

Functions (parser order, reverse-source): helper=1/none, does_real_work=4/none,
  zero_arg_passthrough=1/return_passthrough, keyword_passthrough=1/return_passthrough,
  wrapper_no_transform=1/wrapper_no_transform, assign_delegate=2/assign_delegate,
  passthrough_return=1/return_passthrough.
Statement-count list (sorted): [1, 1, 1, 1, 1, 2, 4]
Delegation kinds: 5 delegates (return_passthrough x3, wrapper_no_transform x1, assign_delegate x1), 2 non-delegates.
"""
from __future__ import annotations


def passthrough_return(a, b):
    return helper(a, b)


def assign_delegate(a, b):
    x = helper(a, b)
    return x


def wrapper_no_transform(a):
    helper(a)


def keyword_passthrough(a, b):
    return helper(a=a, b=b)


def zero_arg_passthrough():
    return helper()


def does_real_work(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def helper(*args, **kwargs):
    return None
