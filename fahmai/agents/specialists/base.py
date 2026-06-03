# -*- coding: utf-8 -*-
"""Shared building blocks for specialist sub-agents (native tool-calling ReAct)."""
from __future__ import annotations

import asyncio

from langgraph.prebuilt import create_react_agent

from fahmai.agents.config import RETRY_ON_TIMEOUT
from fahmai.agents.llm import make_tool_llm

# Gateway timeouts (HTTP 504 / "operation was aborted") are transient — retry them.
_TRANSIENT = ("504", "aborted", "timeout", "timed out", "502", "503", "gateway")


def build_react(prompt: str, tools: list):
    """A ReAct agent bound to `tools` with the given system prompt (uses tool-calling LLM)."""
    return create_react_agent(make_tool_llm(), tools, prompt=prompt)


def _is_transient(err: Exception) -> bool:
    s = str(err).lower()
    return any(t in s for t in _TRANSIENT)


async def run_specialist_async(agent, subq: str, recursion: int) -> str:
    """Run one specialist on a sub-question; retry transient gateway timeouts (504), and never
    crash the graph — report a clearly-labelled message instead."""
    last: Exception | None = None
    for attempt in range(RETRY_ON_TIMEOUT + 1):
        try:
            out = await agent.ainvoke({"messages": [("human", subq)]},
                                      config={"recursion_limit": recursion})
            return out["messages"][-1].content
        except Exception as e:  # noqa: BLE001
            last = e
            if _is_transient(e) and attempt < RETRY_ON_TIMEOUT:
                await asyncio.sleep(2 ** attempt)   # 1s, 2s backoff
                continue
            break
    if last is not None and _is_transient(last):
        return f"(model gateway timeout after {RETRY_ON_TIMEOUT + 1} tries: {str(last)[:100]})"
    return f"(stopped after step budget: {str(last)[:120]})"
