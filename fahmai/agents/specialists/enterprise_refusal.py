# -*- coding: utf-8 -*-
"""Enterprise refusal specialist implementation."""
from __future__ import annotations

from typing import Any, Callable

from fahmai.agents.enterprise_state import EnterpriseState, SpecialistResult
from fahmai.agents.enterprise_utils import (
    EN_PROMPT_INJECTION_PREFIX,
    THAI_PROMPT_INJECTION_PREFIX,
    refusal_answer,
    sanitize_refusal_topic,
)

AppendLog = Callable[[EnterpriseState, dict[str, Any]], list[dict[str, Any]]]


def run(
    state: EnterpriseState,
    subtasks: list[dict[str, Any]],
    append_log: AppendLog,
) -> dict[str, Any]:
    needs_refusal = bool(state.get("validation", {}).get("should_refuse")) or bool(subtasks)
    if not needs_refusal:
        return {}
    validation = state.get("validation") or {}
    rtype = validation.get("refusal_type") or ("prompt_injection" if state.get("is_prompt_injection") else "data_not_found")
    topic = validation.get("refusal_topic") or state.get("refusal_topic") or state.get("safe_underlying_question") or "requested topic"
    topic = sanitize_refusal_topic(str(topic), state.get("safe_underlying_question") or state.get("normalized_question"))
    base_type = "schema_missing" if rtype == "schema_missing" else "data_not_found"
    answer = refusal_answer(str(topic), state.get("language", "en"), base_type)
    if rtype == "prompt_injection":
        prefix = EN_PROMPT_INJECTION_PREFIX if state.get("language") == "en" else THAI_PROMPT_INJECTION_PREFIX
        answer = f"{prefix}\n{answer}"
    result: SpecialistResult = {
        "status": "success",
        "summary": answer,
        "evidence": [],
        "refusal_topic": str(topic),
        "warnings": [],
    }
    specialist_results = dict(state.get("specialist_results") or {})
    specialist_results["refusal"] = result
    return {
        "specialist_results": specialist_results,
        "answer_candidate": answer,
        "final_answer": answer,
        "logs": append_log(state, {"node": "refusal_specialist", "refusal_type": rtype, "topic": topic}),
    }
