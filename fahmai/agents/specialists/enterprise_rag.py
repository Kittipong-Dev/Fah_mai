# -*- coding: utf-8 -*-
"""Enterprise RAG specialist implementation."""
from __future__ import annotations

from typing import Any, Callable

from fahmai.agents.enterprise_state import EnterpriseState, SpecialistResult
from fahmai.agents.rag_specialist import run_rag_specialist_subtasks

AppendLog = Callable[[EnterpriseState, dict[str, Any]], list[dict[str, Any]]]


def run(
    state: EnterpriseState,
    subtasks: list[dict[str, Any]],
    append_log: AppendLog,
) -> dict[str, Any]:
    if not subtasks:
        return {}
    result: SpecialistResult = run_rag_specialist_subtasks(subtasks, state)
    evidence = list(result.get("evidence") or [])
    refusal_topic = result.get("refusal_topic")
    specialist_results = dict(state.get("specialist_results") or {})
    specialist_results["rag"] = result
    return {
        "specialist_results": specialist_results,
        "evidence": list(state.get("evidence") or []) + evidence,
        "refusal_topic": state.get("refusal_topic") or refusal_topic,
        "logs": append_log(
            state,
            {
                "node": "rag_specialist",
                "search_queries": result.get("search_queries", []),
                "attempts": result.get("attempts", []),
                "status": result.get("status"),
            },
        ),
    }
