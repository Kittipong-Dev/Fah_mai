# -*- coding: utf-8 -*-
"""Specialist registry. Each sub-agent is its own module (sql_analyst, doc_researcher);
add a new specialist by dropping a module here and registering it in SPECIALISTS.

Agents are built lazily (no LLM calls at import) and cached.
"""
from __future__ import annotations

from fahmai.agents.specialists import doc_researcher, rag_researcher, sql_analyst
from fahmai.agents.specialists.base import run_specialist_async

# kind -> module (each module exposes build(), KIND, RECURSION)
SPECIALISTS = {
    sql_analyst.KIND: sql_analyst,
    doc_researcher.KIND: doc_researcher,
    rag_researcher.KIND: rag_researcher,
}

_BUILT: dict = {}


def build_specialists() -> dict:
    """Build & cache every specialist agent. Returns {kind: agent}."""
    if not _BUILT:
        for kind, mod in SPECIALISTS.items():
            _BUILT[kind] = mod.build()
    return _BUILT


async def run(kind: str, subq: str) -> str:
    """Route a sub-question to a specialist (defaults to 'sql' for unknown kinds)."""
    agents = build_specialists()
    mod = SPECIALISTS.get(kind, sql_analyst)
    agent = agents.get(kind, agents[sql_analyst.KIND])
    return await run_specialist_async(agent, subq, mod.RECURSION)


__all__ = ["SPECIALISTS", "build_specialists", "run", "run_specialist_async"]
