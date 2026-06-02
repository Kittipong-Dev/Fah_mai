# -*- coding: utf-8 -*-
"""Shared building blocks for specialist sub-agents (native tool-calling ReAct)."""
from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from fahmai.agents.llm import make_llm


def build_react(prompt: str, tools: list):
    """A ReAct agent bound to `tools` with the given system prompt."""
    return create_react_agent(make_llm(), tools, prompt=prompt)


async def run_specialist_async(agent, subq: str, recursion: int) -> str:
    """Run one specialist on a sub-question; never crash the graph — report instead."""
    try:
        out = await agent.ainvoke({"messages": [("human", subq)]},
                                  config={"recursion_limit": recursion})
        return out["messages"][-1].content
    except Exception as e:  # e.g. GraphRecursionError
        return f"(stopped after step budget: {str(e)[:120]})"
