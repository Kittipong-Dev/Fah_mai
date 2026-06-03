# -*- coding: utf-8 -*-
"""Specialist registry. Each sub-agent is its own module (sql_analyst, doc_researcher);
add a new specialist by dropping a module here and registering it in SPECIALISTS.

Agents are built lazily (no LLM calls at import) and cached.
"""
from __future__ import annotations

try:
    from fahmai.agents.specialists import doc_researcher, sql_analyst
    from fahmai.agents.specialists.base import run_specialist_async
except ModuleNotFoundError as _import_error:  # pragma: no cover - bare helper imports without graph deps
    doc_researcher = None
    sql_analyst = None
    _SPECIALIST_IMPORT_ERROR = _import_error

    async def run_specialist_async(*_args, **_kwargs):
        raise _SPECIALIST_IMPORT_ERROR

# kind -> module (each module exposes build(), KIND, RECURSION)
SPECIALISTS = (
    {sql_analyst.KIND: sql_analyst, doc_researcher.KIND: doc_researcher}
    if sql_analyst is not None and doc_researcher is not None
    else {}
)

_BUILT: dict = {}


def build_specialists() -> dict:
    """Build & cache every specialist agent. Returns {kind: agent}."""
    if not SPECIALISTS:
        raise _SPECIALIST_IMPORT_ERROR
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
