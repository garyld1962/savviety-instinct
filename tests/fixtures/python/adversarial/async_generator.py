"""Adversarial fixture: async def + yield, async for, async with.

Mixes async-generator semantics (async def that yields), async iteration,
async context management, and an awaited-return that resembles trivial
passthrough but is explicitly Known-Gap per trivial_delegation_ratio's R1
rules (async bodies do not classify as passthrough).

Expected:
  functions: 3 (gen_chunks, gather, passthrough)
  all delegation_kind: NONE (passthrough excluded by R1 async gap)
"""
from __future__ import annotations


async def gen_chunks(source):
    async for chunk in source:
        yield chunk


async def gather(context_factory):
    async with context_factory() as ctx:
        result = []
        async for item in ctx:
            result.append(item)
        return result


async def passthrough(source):
    return await source.read()
