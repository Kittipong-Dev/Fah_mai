# -*- coding: utf-8 -*-
"""Node implementations for the enterprise data-agent graph."""
from __future__ import annotations

import re
from typing import Any

from fahmai.agents.config import REPLAN_BUDGET
from fahmai.agents.enterprise_state import EnterpriseState
from fahmai.agents.enterprise_utils import (
    build_terms,
    detect_language,
    extract_entities,
    fallback_plan,
    is_wellformed_refusal,
    needs_thai_language_rewrite,
    normalize_fiscal_expressions,
    normalize_month_names,
    normalize_years,
    refusal_answer,
    remove_forced_strings,
    sanitize_refusal_topic,
    safe_json_loads,
    validate_plan,
)
from fahmai.agents.guardrails.input_guard import scan_input
from fahmai.agents.llm import make_llm
from fahmai.agents.prompts.enterprise import (
    ANSWER_CHECKER_SYS,
    FINAL_ANALYZER_SYS,
    LANGUAGE_GUARD_SYS,
    LLM_INJECTION_GUARDRAIL_SYS,
    PLANNER_ENTERPRISE_SYS,
)
from fahmai.agents.query_log import append_query_log
from fahmai.agents.rule_normalizer import normalize_question_rule_based
from fahmai.agents.specialists import (
    enterprise_compute,
    enterprise_rag,
    enterprise_refusal,
    enterprise_sql,
)

_EXTRA_INJECTION = {
    "developer_instruction": re.compile(r"developer instruction", re.I),
    "ignore_previous": re.compile(r"ignore (?:all )?(?:previous|prior) instructions", re.I),
    "authoritative_memo": re.compile(r"authoritative memo", re.I),
    "reply_exact": re.compile(r"reply with (?:the )?exact string|output exactly", re.I),
    "hidden_instruction": re.compile(r"hidden instruction", re.I),
    "unsupported_confirm": re.compile(r"confirm unsupported|confirm .*facts?", re.I),
    "no_internal_table": re.compile(r"do not use internal table", re.I),
    "canary_assignment": re.compile(r"\bCONFIRMED_[A-Z0-9_]+\s*=\s*\S+", re.I),
    "system_tag": re.compile(r"\[\s*/?\s*system\b[^\]]*\]|</?\s*system\s*>|<\|\s*[^|]*\|>|<\s*im_start\s*>|<\|start_header_id\|>", re.I),
    "faux_reasoning": re.compile(r"</?\s*(think|scratchpad|reasoning)\s*>", re.I),
    "trust_claim": re.compile(r"trust\s*[=:]\s*high|admin\s*mode|system\s*override|certified\s+admin|verified\s+admin", re.I),
    "fake_session_continuity": re.compile(r"(previous|earlier|last)\s+session|you (already )?confirmed|as (we )?agreed", re.I),
    "leading_confirm": re.compile(r"(correct|right|true)\s*\?$|i\s+(vaguely\s+)?remember", re.I),
    "exfil_request": re.compile(r"(copy|paste|forward|send)[^\n]{0,40}(link|url|confirmation)|forward[^\n]{0,30}(@|email)", re.I),
}

_OUTPUT_CANARY_RE = re.compile(r"\bCONFIRMED_[A-Z0-9_]+\s*=\s*\S+|\bCONFIRMED_[A-Z0-9_]+\b", re.I)
_OUTPUT_CONFIRM_LINK_RE = re.compile(r"https?://\S*(confirm|token|reset|verify|otp)\S*", re.I)


def _merge_lists(*values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        items = value if isinstance(value, list) else [value] if value else []
        for item in items:
            clean = str(item).strip()
            if clean and clean not in seen:
                out.append(clean)
                seen.add(clean)
    return out


def _merge_rule_normalization(
    entities: dict[str, Any],
    terms: dict[str, list[str]],
    dates: dict[str, Any],
    rule: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = dict(entities)
    rule_entities = rule.get("entities") or {}
    for key, values in rule_entities.items():
        if isinstance(values, list):
            merged[key] = _merge_lists(merged.get(key), values)

    sql_terms = rule.get("sql_terms") or {}
    rag_terms = rule.get("rag_terms") or {}
    log_terms = rule.get("log_terms") or {}
    routing_hints = rule.get("routing_hints") or {}
    rule_date_terms: list[str] = []
    for item in rule.get("date_constraints") or []:
        if isinstance(item, dict):
            rule_date_terms.extend(
                str(value)
                for key in ("start", "end", "raw")
                for value in [item.get(key)]
                if value
            )
            for key in ("start", "end"):
                value = str(item.get(key) or "")
                if re.match(r"^20\d{2}-", value):
                    rule_date_terms.append(value[:4])

    merged["search_keywords"] = _merge_lists(
        terms.get("search_keywords"),
        rule_date_terms,
        rule_entities.get("sku_ids"),
        rule_entities.get("vendor_ids"),
        rule_entities.get("employee_ids"),
        rule_entities.get("customer_ids"),
        rule_entities.get("branch_codes"),
        rule_entities.get("branch_filter_hints"),
        rule_entities.get("campaign_ids"),
        rule_entities.get("invoice_ids"),
        rule_entities.get("return_ids"),
        rule_entities.get("refund_ids"),
        rule_entities.get("claim_ids"),
        rule_entities.get("aliases"),
        sql_terms.get("table_hints"),
        sql_terms.get("metric_hints"),
        rag_terms.get("rag_keywords"),
        rag_terms.get("event_markers"),
    )
    merged["sql_terms"] = _merge_lists(
        terms.get("sql_terms"),
        sql_terms.get("explicit_tables"),
        sql_terms.get("table_hints"),
        sql_terms.get("column_hints"),
        sql_terms.get("metric_hints"),
        sql_terms.get("operation_hints"),
        rule_entities.get("branch_filter_hints"),
    )
    merged["aliases"] = _merge_lists(terms.get("aliases"), rule_entities.get("aliases"))
    merged["table_hints"] = _merge_lists(sql_terms.get("table_hints"))
    merged["explicit_tables"] = _merge_lists(sql_terms.get("explicit_tables"))
    merged["column_hints"] = _merge_lists(sql_terms.get("column_hints"))
    merged["metric_hints"] = _merge_lists(sql_terms.get("metric_hints"))
    merged["operation_hints"] = _merge_lists(sql_terms.get("operation_hints"))
    merged["doc_families"] = _merge_lists(rag_terms.get("doc_families"))
    merged["rag_keywords"] = _merge_lists(rag_terms.get("rag_keywords"))
    merged["event_markers"] = _merge_lists(rag_terms.get("event_markers"))
    merged["log_families"] = _merge_lists(log_terms.get("log_families"))
    merged["line_id_hints"] = _merge_lists(log_terms.get("line_id_hints"))
    merged["question_shape"] = rule.get("question_shape") or {}
    merged["routing_hints"] = routing_hints
    merged["date_axis"] = rule.get("date_axis") or {}
    merged["normalizer_constraints"] = rule.get("constraints") or {}
    merged["normalizer_warnings"] = rule.get("warnings") or []
    merged["unresolved_terms"] = rule.get("unresolved_terms") or []

    merged_dates = dict(dates)
    if rule.get("date_axis"):
        merged_dates["default_date_axis"] = rule.get("date_axis")
    if rule.get("date_constraints"):
        merged_dates["rule_date_ranges"] = rule.get("date_constraints")
    return merged, merged_dates


def _apply_plan_hints(plan: dict[str, Any], state: EnterpriseState) -> dict[str, Any]:
    entities = state.get("normalized_entities") or {}
    branch_codes = {str(value).upper() for value in entities.get("branch_codes", [])}
    if "REMOTE" not in branch_codes:
        return plan

    def fix_remote_branch(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        fixed = text
        fixed = re.sub(r"branches?\s+with\s+branch_type\s*=\s*['\"]remote['\"]", "branch_code = 'REMOTE'", fixed, flags=re.I)
        fixed = re.sub(r"branch_type\s*=\s*['\"]REMOTE['\"]", "branch_code = 'REMOTE'", fixed, flags=re.I)
        fixed = re.sub(r"branch_type\s*=\s*['\"]remote['\"]", "branch_code = 'REMOTE'", fixed, flags=re.I)
        fixed = re.sub(r"\bREMOTE\s+branches\b", "branch_code = 'REMOTE'", fixed, flags=re.I)
        fixed = re.sub(r"\bremote\s+branches\b", "branch_code = 'REMOTE'", fixed, flags=re.I)
        return fixed

    fixed_plan = dict(plan)
    fixed_subtasks = []
    changed = False
    for st in fixed_plan.get("subtasks") or []:
        new_st = dict(st)
        for key in ("task", "expected_output"):
            value = fix_remote_branch(new_st.get(key))
            if value != new_st.get(key):
                changed = True
                new_st[key] = value
        fixed_subtasks.append(new_st)
    if changed:
        fixed_plan["subtasks"] = fixed_subtasks
        risk_flags = list(fixed_plan.get("risk_flags") or [])
        risk_flags.append("normalized REMOTE branch reference to branch_code='REMOTE'")
        fixed_plan["risk_flags"] = list(dict.fromkeys(risk_flags))
    return fixed_plan


def _llm_json(system: str, human: str) -> dict[str, Any]:
    try:
        out = make_llm(0.0).invoke([("system", system), ("human", human)]).content
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}
    return safe_json_loads(out)


def _append_log(state: EnterpriseState, event: dict[str, Any]) -> list[dict[str, Any]]:
    logs = list(state.get("logs") or [])
    logs.append(event)
    append_query_log(
        {
            "raw_question": state.get("raw_question"),
            "normalized_question": state.get("normalized_question"),
            "classification": state.get("question_type"),
            **event,
        }
    )
    return logs


def question_intake_node(state: EnterpriseState) -> dict[str, Any]:
    raw = state.get("raw_question") or state.get("normalized_question") or ""
    entities = extract_entities(raw)
    dates = {"dates": entities.get("dates", [])}
    return {
        "raw_question": raw,
        "language": detect_language(raw),
        "normalized_entities": entities,
        "date_constraints": dates,
        "safe_underlying_question": raw,
        "errors": state.get("errors") or [],
        "logs": _append_log(state, {"node": "question_intake", "entities": entities}),
    }


def question_normalizer_node(state: EnterpriseState) -> dict[str, Any]:
    raw = state.get("raw_question", "")
    normalized, year_meta = normalize_years(raw)
    normalized, fiscal_meta = normalize_fiscal_expressions(normalized)
    normalized, month_meta = normalize_month_names(normalized)
    entities = extract_entities(normalized)
    terms = build_terms(normalized, entities)
    dates = {
        **(state.get("date_constraints") or {}),
        **year_meta,
        **fiscal_meta,
        **month_meta,
        "dates": entities.get("dates", []),
    }
    rule = normalize_question_rule_based(normalized, str(state.get("question_id") or ""))
    rule_entities, dates = _merge_rule_normalization(entities, terms, dates, rule)
    all_entities = {**(state.get("normalized_entities") or {}), **rule_entities}
    return {
        "normalized_question": normalized,
        "normalized_entities": all_entities,
        "date_constraints": dates,
        "logs": _append_log(
            state,
            {
                "node": "question_normalizer",
                "normalized_question": normalized,
                "table_hints": all_entities.get("table_hints", []),
                "routing_hints": all_entities.get("routing_hints", {}),
                "normalizer_warnings": all_entities.get("normalizer_warnings", []),
            },
        ),
    }


def rule_based_injection_guardrail_node(state: EnterpriseState) -> dict[str, Any]:
    question = state.get("normalized_question") or state.get("raw_question") or ""
    flags = scan_input(question)
    reasons = list(flags.directives)
    for name, rx in _EXTRA_INJECTION.items():
        if rx.search(question):
            reasons.append(name)
    safe = question
    safe = re.sub(r"\[\s*/?\s*SYSTEM\s*\]", " ", safe, flags=re.I)
    safe = re.sub(r"\[\s*/?\s*system\b[^\]]*\]|</?\s*system\s*>|<\|\s*[^|]*\|>|<\s*im_start\s*>|<\|start_header_id\|>", " ", safe, flags=re.I)
    safe = re.sub(r"</?\s*(think|scratchpad|reasoning)\s*>", " ", safe, flags=re.I)
    safe = re.sub(r"(?i)(ignore .*?instructions|reply with .*?exact string|output exactly .*?$)", " ", safe)
    safe = re.sub(r"\s{2,}", " ", safe).strip() or question
    is_injection = bool(reasons) or bool(flags.authority_grant)
    if flags.authority_grant and "authority_grant" not in reasons:
        reasons.append("authority_grant")
    return {
        "is_prompt_injection": bool(state.get("is_prompt_injection")) or is_injection,
        "injection_reasons": list(dict.fromkeys((state.get("injection_reasons") or []) + reasons)),
        "safe_underlying_question": safe,
        "logs": _append_log(state, {"node": "rule_injection_guardrail", "is_prompt_injection": is_injection, "reasons": reasons}),
    }


def llm_injection_guardrail_node(state: EnterpriseState) -> dict[str, Any]:
    question = state.get("normalized_question") or state.get("raw_question") or ""
    payload = _llm_json(LLM_INJECTION_GUARDRAIL_SYS, question)
    if payload.get("_error"):
        return {
            "logs": _append_log(state, {"node": "llm_injection_guardrail", "status": "skipped", "error": payload["_error"][:160]})
        }
    is_injection = bool(payload.get("is_prompt_injection"))
    reasons = list(state.get("injection_reasons") or [])
    if is_injection:
        reasons.append(str(payload.get("injected_span_summary") or "llm_detected"))
    if is_injection:
        safe = str(payload.get("safe_underlying_question") or state.get("safe_underlying_question") or question)
    else:
        safe = state.get("safe_underlying_question") or question
    return {
        "is_prompt_injection": bool(state.get("is_prompt_injection")) or is_injection,
        "injection_reasons": list(dict.fromkeys(reasons)),
        "safe_underlying_question": safe,
        "logs": _append_log(state, {"node": "llm_injection_guardrail", "result": payload}),
    }


def question_classifier_node(state: EnterpriseState) -> dict[str, Any]:
    q = (state.get("safe_underlying_question") or state.get("normalized_question") or "").lower()
    hints = (state.get("normalized_entities") or {}).get("routing_hints") or {}
    if state.get("is_prompt_injection"):
        qtype = "prompt_injection"
    elif hints.get("requires_finance_compute"):
        qtype = "finance_compute"
    elif hints.get("requires_rag") and hints.get("requires_sql"):
        qtype = "hybrid_sql_rag"
    elif hints.get("requires_rag"):
        qtype = "document_lookup"
    elif re.search(r"\b(roi|yoy|variance|percentage|share|reconcile|gap|mismatch|compare|growth)\b", q, re.I):
        qtype = "finance_compute"
    elif re.search(r"\b(policy|memo|email|chat|line works|document|thread|faq|minutes|explain|context)\b", q, re.I):
        qtype = "document_lookup"
    elif re.search(r"\b(count|sum|total|average|avg|rank|ranking|group by|top|bottom|between)\b", q, re.I):
        qtype = "sql_aggregation"
    elif re.search(r"\b(schema|column|field|table)\b", q, re.I):
        qtype = "simple_sql_lookup"
    elif not q.strip():
        qtype = "unknown"
    else:
        qtype = "simple_sql_lookup"
    return {
        "question_type": qtype,
        "logs": _append_log(state, {"node": "question_classifier", "question_type": qtype}),
    }


def planner_node(state: EnterpriseState) -> dict[str, Any]:
    question = state.get("safe_underlying_question") or state.get("normalized_question") or ""
    context = {
        "question": question,
        "classification": state.get("question_type"),
        "entities": state.get("normalized_entities"),
        "date_constraints": state.get("date_constraints"),
        "is_prompt_injection": state.get("is_prompt_injection", False),
        "injection_reasons": state.get("injection_reasons", []),
    }
    payload = _llm_json(PLANNER_ENTERPRISE_SYS, str(context))
    if payload.get("_error") or not payload:
        plan = fallback_plan(question, state.get("question_type", "unknown"))
        errors = [payload.get("_error", "planner returned no JSON")] if payload else ["planner returned no JSON"]
    else:
        plan, errors = validate_plan(payload)
        if not plan.get("goal"):
            plan["goal"] = question
    plan = _apply_plan_hints(plan, state)
    return {
        "plan": plan,
        "errors": list(state.get("errors") or []) + errors,
        "logs": _append_log(state, {"node": "planner", "plan": plan, "errors": errors}),
    }


def planner_json_validation_hook(state: EnterpriseState) -> dict[str, Any]:
    plan, errors = validate_plan(state.get("plan") or {})
    if errors:
        repaired, repair_errors = validate_plan({**fallback_plan(state.get("safe_underlying_question", ""), state.get("question_type", "unknown")), **plan})
        plan = repaired
        errors.extend(repair_errors)
    plan = _apply_plan_hints(plan, state)
    return {
        "plan": plan,
        "errors": list(state.get("errors") or []) + errors,
        "logs": _append_log(state, {"node": "planner_json_validation", "errors": errors}),
    }


def _subtasks_for(state: EnterpriseState, specialist: str) -> list[dict[str, Any]]:
    return [st for st in (state.get("plan", {}).get("subtasks") or []) if st.get("specialist") == specialist]


def planned_worker_groups(state: EnterpriseState) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for st in state.get("plan", {}).get("subtasks") or []:
        specialist = st.get("specialist")
        if specialist in {"sql", "rag", "refusal"}:
            groups.setdefault(str(specialist), []).append(st)
    return groups


def has_pending_compute(state: EnterpriseState) -> bool:
    return bool(_subtasks_for(state, "finance_compute")) and "finance_compute" not in (state.get("specialist_results") or {})


def specialist_worker_node(state: EnterpriseState) -> dict[str, Any]:
    specialist = str(state.get("active_specialist") or "")
    worker_state: EnterpriseState = {
        **state,
        "logs": [],
        "evidence": [],
        "final_answer": "",
        "answer_candidate": "",
    }
    subtasks = list(state.get("active_subtasks") or [])
    if specialist == "sql":
        result = enterprise_sql.run(worker_state, subtasks, _llm_json, _append_log)
    elif specialist == "rag":
        result = enterprise_rag.run(worker_state, subtasks, _append_log)
    elif specialist == "refusal":
        result = enterprise_refusal.run(worker_state, subtasks, _append_log)
    else:
        result = {"logs": _append_log(worker_state, {"node": "specialist_worker", "status": "unknown", "specialist": specialist})}
    return {
        "worker_outputs": [
            {
                "attempt": int(state.get("active_attempt") or 0),
                "specialist": specialist,
                "result": result,
            }
        ]
    }


def aggregate_specialist_outputs_node(state: EnterpriseState) -> dict[str, Any]:
    attempt = int(state.get("replan_attempts") or 0)
    outputs = [out for out in state.get("worker_outputs", []) if out.get("attempt") == attempt]
    specialist_results = dict(state.get("specialist_results") or {})
    evidence = list(state.get("evidence") or [])
    logs = list(state.get("logs") or [])
    refusal_topic = state.get("refusal_topic")
    final_answer = state.get("final_answer")
    answer_candidate = state.get("answer_candidate")

    for out in outputs:
        result = out.get("result") or {}
        specialist_results.update(result.get("specialist_results") or {})
        evidence.extend(result.get("evidence") or [])
        logs.extend(result.get("logs") or [])
        if result.get("refusal_topic"):
            refusal_topic = refusal_topic or result.get("refusal_topic")
        if result.get("final_answer"):
            final_answer = result.get("final_answer")
        if result.get("answer_candidate"):
            answer_candidate = result.get("answer_candidate")

    logs = _append_log(
        {**state, "logs": logs},
        {
            "node": "aggregate_specialist_outputs",
            "attempt": attempt,
            "specialists": [out.get("specialist") for out in outputs],
        },
    )
    return {
        "specialist_results": specialist_results,
        "evidence": evidence,
        "logs": logs,
        "refusal_topic": refusal_topic,
        "final_answer": final_answer,
        "answer_candidate": answer_candidate,
    }


def sql_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    return enterprise_sql.run(state, _subtasks_for(state, "sql"), _llm_json, _append_log)


def rag_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    return enterprise_rag.run(state, _subtasks_for(state, "rag"), _append_log)


def finance_compute_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    return enterprise_compute.run(state, _subtasks_for(state, "finance_compute"), _llm_json, _append_log)


def specialist_coverage_node(state: EnterpriseState) -> dict[str, Any]:
    results = state.get("specialist_results") or {}
    required = [st for st in state.get("plan", {}).get("subtasks", []) if st.get("required", True)]
    failed = []
    for st in required:
        specialist = str(st.get("specialist") or "")
        res = results.get(specialist)
        if res and res.get("status") == "error":
            failed.append(st)
    attempts = int(state.get("replan_attempts") or 0)
    if failed and attempts < REPLAN_BUDGET:
        plan = dict(state.get("plan") or {})
        plan["subtasks"] = failed
        return {
            "plan": plan,
            "failed_subtasks": failed,
            "replan_attempts": attempts + 1,
            "logs": _append_log(
                state,
                {
                    "node": "specialist_coverage",
                    "action": "retry_failed_subtasks",
                    "failed_ids": [st.get("id") for st in failed],
                    "attempt": attempts + 1,
                },
            ),
        }
    return {
        "failed_subtasks": [],
        "logs": _append_log(
            state,
            {
                "node": "specialist_coverage",
                "action": "continue",
                "failed_ids": [st.get("id") for st in failed],
                "attempt": attempts,
            },
        ),
    }


def route_specialist_coverage(state: EnterpriseState) -> str:
    if state.get("failed_subtasks"):
        return "planner_json_validation"
    if has_pending_compute(state):
        return "finance_compute_specialist"
    return "evidence_validator"


def refusal_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    return enterprise_refusal.run(state, _subtasks_for(state, "refusal"), _append_log)


def evidence_validator_node(state: EnterpriseState) -> dict[str, Any]:
    evidence = state.get("evidence") or []
    results = state.get("specialist_results") or {}
    unsupported: list[str] = []
    missing: list[str] = []
    refusal_type = None
    refusal_topic = state.get("refusal_topic") or state.get("safe_underlying_question")
    required = [st for st in state.get("plan", {}).get("subtasks", []) if st.get("required", True)]
    for st in required:
        res = results.get(st.get("specialist"))
        if res and st.get("specialist") == "finance_compute" and res.get("status") == "missing_input" and evidence:
            continue
        if not res or res.get("status") in {"no_data", "schema_missing", "missing_input", "error"}:
            missing.append(str(st.get("task") or st.get("id")))
            refusal_topic = sanitize_refusal_topic(
                res.get("refusal_topic") if res else str(st.get("task") or st.get("id")),
                state.get("safe_underlying_question") or state.get("normalized_question"),
            )
            if res and res.get("status") == "schema_missing":
                refusal_type = "schema_missing"
    if not evidence and required:
        missing.append("no verified evidence")
    if state.get("is_prompt_injection") and state.get("answer_candidate"):
        answer_lower = state["answer_candidate"].lower()
        for reason in state.get("injection_reasons", []):
            if reason and reason.lower() in answer_lower:
                unsupported.append(f"answer echoes injected directive: {reason}")
                refusal_type = "prompt_injection"
    should_refuse = bool(missing or unsupported)
    if should_refuse and not refusal_type:
        refusal_type = "prompt_injection" if state.get("is_prompt_injection") and not evidence else "data_not_found"
    validation = {
        "is_supported": not should_refuse,
        "unsupported_claims": unsupported,
        "missing_required_evidence": list(dict.fromkeys(missing)),
        "should_refuse": should_refuse,
        "refusal_type": refusal_type,
        "refusal_topic": refusal_topic,
        "confidence": "high" if not should_refuse else "medium",
    }
    return {
        "validation": validation,
        "refusal_topic": refusal_topic,
        "logs": _append_log(state, {"node": "evidence_validator", "validation": validation}),
    }


def final_analyzer_node(state: EnterpriseState) -> dict[str, Any]:
    if state.get("validation", {}).get("should_refuse") and state.get("final_answer"):
        return {}
    if state.get("validation", {}).get("should_refuse"):
        return refusal_specialist_node(state)
    payload = {
        "question": state.get("safe_underlying_question") or state.get("normalized_question"),
        "language": state.get("language"),
        "evidence": state.get("evidence", []),
        "specialist_results": state.get("specialist_results", {}),
        "validation": state.get("validation", {}),
        "prompt_injection": state.get("is_prompt_injection", False),
    }
    try:
        answer = make_llm(0.0).invoke([("system", FINAL_ANALYZER_SYS), ("human", str(payload))]).content
    except Exception:
        snippets = [str(ev.get("value") or ev.get("quote_or_snippet") or ev.get("claim")) for ev in state.get("evidence", [])]
        answer = "\n".join(snippets[:2]) if snippets else refusal_answer(str(state.get("refusal_topic") or payload["question"]), state.get("language", "en"))
    return {
        "answer_candidate": answer,
        "final_answer": answer,
        "logs": _append_log(state, {"node": "final_analyzer", "answer_len": len(answer or "")}),
    }


def language_guard_node(state: EnterpriseState) -> dict[str, Any]:
    answer = str(state.get("final_answer") or state.get("answer_candidate") or "")
    language = state.get("language", "en")
    if not needs_thai_language_rewrite(language, answer):
        return {
            "logs": _append_log(
                state,
                {"node": "language_guard", "rewritten": False, "language": language},
            )
        }
    payload = {
        "question": state.get("safe_underlying_question") or state.get("normalized_question"),
        "answer": answer,
        "language": language,
    }
    try:
        rewritten = make_llm(0.0).invoke([("system", LANGUAGE_GUARD_SYS), ("human", str(payload))]).content
        rewritten = str(rewritten or "").strip()
    except Exception as exc:  # noqa: BLE001
        return {
            "logs": _append_log(
                state,
                {
                    "node": "language_guard",
                    "rewritten": False,
                    "language": language,
                    "error": str(exc)[:160],
                },
            )
        }
    if not rewritten:
        return {
            "logs": _append_log(
                state,
                {"node": "language_guard", "rewritten": False, "language": language, "error": "empty rewrite"},
            )
        }
    return {
        "answer_candidate": rewritten,
        "final_answer": rewritten,
        "logs": _append_log(
            state,
            {
                "node": "language_guard",
                "rewritten": True,
                "language": language,
                "answer_len_before": len(answer),
                "answer_len_after": len(rewritten),
            },
        ),
    }


def answer_checker_node(state: EnterpriseState) -> dict[str, Any]:
    answer = state.get("final_answer") or state.get("answer_candidate") or ""
    payload = _llm_json(
        ANSWER_CHECKER_SYS,
        str(
            {
                "question": state.get("safe_underlying_question") or state.get("normalized_question"),
                "answer": answer,
                "validation": state.get("validation"),
                "injection_reasons": state.get("injection_reasons", []),
            }
        ),
    )
    issues = list(payload.get("issues") or []) if payload and not payload.get("_error") else []
    passed = bool(payload.get("pass", True)) if payload and not payload.get("_error") else True
    if state.get("validation", {}).get("should_refuse") and not is_wellformed_refusal(answer):
        passed = False
        issues.append("refusal is not well formed")
        answer = refusal_answer(
            sanitize_refusal_topic(
                str(state.get("validation", {}).get("refusal_topic") or state.get("refusal_topic") or ""),
                state.get("safe_underlying_question") or state.get("normalized_question"),
            ),
            state.get("language", "en"),
            "schema_missing" if state.get("validation", {}).get("refusal_type") == "schema_missing" else "data_not_found",
        )
    return {
        "final_answer": answer,
        "logs": _append_log(state, {"node": "answer_checker", "pass": passed, "issues": issues}),
    }


def output_formatter_hook(state: EnterpriseState) -> dict[str, Any]:
    answer = str(state.get("final_answer") or state.get("answer_candidate") or "")
    answer = re.sub(r"```(?:json)?[\s\S]*?```", "", answer).strip()
    answer = _OUTPUT_CANARY_RE.sub("", answer)
    answer = _OUTPUT_CONFIRM_LINK_RE.sub("", answer)
    answer = remove_forced_strings(answer, state.get("injection_reasons", []))
    if state.get("validation", {}).get("should_refuse") and not is_wellformed_refusal(answer):
        answer = refusal_answer(
            sanitize_refusal_topic(
                str(state.get("validation", {}).get("refusal_topic") or state.get("refusal_topic") or ""),
                state.get("safe_underlying_question") or state.get("normalized_question"),
            ),
            state.get("language", "en"),
            "schema_missing" if state.get("validation", {}).get("refusal_type") == "schema_missing" else "data_not_found",
        )
    return {
        "final_answer": answer,
        "logs": _append_log(state, {"node": "output_formatter", "answer_len": len(answer)}),
    }
