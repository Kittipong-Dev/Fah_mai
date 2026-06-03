# -*- coding: utf-8 -*-
"""Enterprise finance/compute specialist implementation."""
from __future__ import annotations

from typing import Any, Callable

from fahmai.agents.enterprise_state import EnterpriseState, SpecialistResult
from fahmai.agents.prompts.enterprise import FINANCE_SPECIALIST_SYS
from fahmai.tools.compute_tool import compute_batch

JsonLLM = Callable[[str, str], dict[str, Any]]
AppendLog = Callable[[EnterpriseState, dict[str, Any]], list[dict[str, Any]]]


def _normalize_payload(payload: dict[str, Any], state: EnterpriseState) -> dict[str, Any]:
    if payload.get("_error") or not payload:
        return {
            "status": "missing_input",
            "inputs_used": [],
            "calculations": [],
            "summary": "Required verified numeric inputs are missing.",
            "evidence": [],
            "refusal_topic": state.get("safe_underlying_question"),
            "warnings": [payload.get("_error", "compute returned no JSON") if payload else "compute returned no JSON"],
        }

    calculations = payload.get("calculations")
    if isinstance(calculations, list) and calculations and any("operation" in c for c in calculations if isinstance(c, dict)):
        computed = compute_batch({"calculations": calculations})
        warnings = list(payload.get("warnings") or []) + list(computed.get("warnings") or [])
        if computed.get("status") in {"success", "partial"}:
            payload = {
                **payload,
                "status": "success" if computed.get("status") == "success" else "missing_input",
                "calculations": computed.get("calculations", []),
                "summary": computed.get("summary") or payload.get("summary") or "",
                "warnings": warnings,
            }
        else:
            payload = {**payload, "status": "missing_input", "warnings": warnings}
    return payload


def run(
    state: EnterpriseState,
    subtasks: list[dict[str, Any]],
    llm_json: JsonLLM,
    append_log: AppendLog,
) -> dict[str, Any]:
    if not subtasks:
        return {}
    payload = llm_json(
        FINANCE_SPECIALIST_SYS,
        str(
            {
                "question": state.get("safe_underlying_question"),
                "subtasks": subtasks,
                "specialist_results": state.get("specialist_results", {}),
            }
        ),
    )
    payload = _normalize_payload(payload, state)
    calculations = list(payload.get("calculations") or [])
    evidence = list(payload.get("evidence") or [])
    if payload.get("status") == "success" and calculations and not evidence:
        evidence = [
            {
                "source": "compute",
                "claim": str(calc.get("label") or calc.get("operation") or "calculation"),
                "value": calc,
            }
            for calc in calculations
        ]
    result: SpecialistResult = {
        "status": str(payload.get("status") or "missing_input"),
        "summary": str(payload.get("summary") or ""),
        "evidence": evidence,
        "refusal_topic": payload.get("refusal_topic"),
        "warnings": list(payload.get("warnings") or []),
    }
    result["rows"] = [{"inputs_used": payload.get("inputs_used", []), "calculations": calculations}]
    specialist_results = dict(state.get("specialist_results") or {})
    specialist_results["finance_compute"] = result
    return {
        "specialist_results": specialist_results,
        "evidence": list(state.get("evidence") or []) + result.get("evidence", []),
        "refusal_topic": state.get("refusal_topic") or result.get("refusal_topic"),
        "logs": append_log(state, {"node": "finance_compute", "status": result["status"]}),
    }
