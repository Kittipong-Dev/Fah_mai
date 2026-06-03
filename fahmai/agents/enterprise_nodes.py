# -*- coding: utf-8 -*-
"""Node implementations for the enterprise data-agent graph."""
from __future__ import annotations

import re
from typing import Any

from fahmai.agents.config import ENTERPRISE_TOP_K
from fahmai.agents.enterprise_state import EnterpriseState, SpecialistResult
from fahmai.agents.enterprise_utils import (
    EN_PROMPT_INJECTION_PREFIX,
    THAI_PROMPT_INJECTION_PREFIX,
    build_terms,
    detect_language,
    extract_entities,
    fallback_plan,
    is_valid_readonly_sql,
    is_wellformed_refusal,
    normalize_fiscal_expressions,
    normalize_month_names,
    normalize_years,
    refusal_answer,
    remove_forced_strings,
    safe_json_loads,
    strip_sql_fences,
    validate_plan,
)
from fahmai.agents.guardrails.input_guard import scan_input
from fahmai.agents.llm import make_llm
from fahmai.agents.prompts.enterprise import (
    ANSWER_CHECKER_SYS,
    COMPUTE_SYS,
    FINAL_ANALYZER_SYS,
    LLM_INJECTION_GUARDRAIL_SYS,
    PLANNER_ENTERPRISE_SYS,
    SQL_GENERATOR_SYS,
)
from fahmai.agents.query_log import append_query_log

_EXTRA_INJECTION = {
    "developer_instruction": re.compile(r"developer instruction", re.I),
    "ignore_previous": re.compile(r"ignore (?:all )?(?:previous|prior) instructions", re.I),
    "authoritative_memo": re.compile(r"authoritative memo", re.I),
    "reply_exact": re.compile(r"reply with (?:the )?exact string|output exactly", re.I),
    "hidden_instruction": re.compile(r"hidden instruction", re.I),
    "unsupported_confirm": re.compile(r"confirm unsupported|confirm .*facts?", re.I),
    "no_internal_table": re.compile(r"do not use internal table", re.I),
}


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
    all_entities = {**(state.get("normalized_entities") or {}), **entities, **terms}
    dates = {
        **(state.get("date_constraints") or {}),
        **year_meta,
        **fiscal_meta,
        **month_meta,
        "dates": entities.get("dates", []),
    }
    return {
        "normalized_question": normalized,
        "normalized_entities": all_entities,
        "date_constraints": dates,
        "logs": _append_log(state, {"node": "question_normalizer", "normalized_question": normalized}),
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
    if state.get("is_prompt_injection"):
        qtype = "prompt_injection"
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
    return {
        "plan": plan,
        "errors": list(state.get("errors") or []) + errors,
        "logs": _append_log(state, {"node": "planner_json_validation", "errors": errors}),
    }


def _subtasks_for(state: EnterpriseState, specialist: str) -> list[dict[str, Any]]:
    return [st for st in (state.get("plan", {}).get("subtasks") or []) if st.get("specialist") == specialist]


def sql_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    subtasks = _subtasks_for(state, "sql")
    if not subtasks:
        return {}
    from fahmai.tools.sql_tool import sql_query

    all_queries: list[str] = []
    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    status = "success"
    refusal_topic: str | None = None
    for st in subtasks:
        payload = _llm_json(
            SQL_GENERATOR_SYS,
            str(
                {
                    "normalized_question": state.get("normalized_question"),
                    "task": st.get("task"),
                    "depends_on": st.get("depends_on", []),
                    "entities": state.get("normalized_entities"),
                    "date_constraints": state.get("date_constraints"),
                    "prior_specialist_results": state.get("specialist_results", {}),
                    "prior_sql_rows": rows,
                }
            ),
        )
        if payload.get("_error"):
            if not evidence:
                status = "error"
            warnings.append(payload["_error"][:160])
            continue
        if payload.get("status") == "schema_missing":
            if not evidence:
                status = "schema_missing"
            refusal_topic = payload.get("refusal_topic") or st.get("task")
            warnings.extend(payload.get("warnings") or [])
            continue
        queries = [strip_sql_fences(q) for q in payload.get("queries", []) if q]
        if not queries:
            if not evidence:
                status = "schema_missing"
            refusal_topic = st.get("task")
            warnings.append("SQL generator returned no query.")
            continue
        for sql in queries[:3]:
            if not is_valid_readonly_sql(sql):
                status = "error"
                warnings.append(f"Blocked non-read-only SQL: {sql[:120]}")
                continue
            result = sql_query(sql)
            all_queries.append(sql)
            row = {"task_id": st.get("id"), "sql": sql, "result": result}
            rows.append(row)
            if result.startswith("SQL ERROR:"):
                if not evidence:
                    status = "error"
                warnings.append(result)
            elif result.strip() == "(0 rows)":
                if status != "error" and not evidence:
                    status = "no_data"
                refusal_topic = refusal_topic or st.get("task")
            else:
                evidence.append(
                    {
                        "source": "postgres",
                        "table_or_view": "query_result",
                        "claim": st.get("task") or "",
                        "value": result,
                    }
                )
                status = "success"
                refusal_topic = None
    if evidence:
        status = "success"
    result: SpecialistResult = {
        "status": status,
        "queries": all_queries,
        "rows": rows,
        "summary": "SQL queries executed." if evidence else "No SQL evidence found.",
        "evidence": evidence,
        "refusal_topic": refusal_topic,
        "warnings": warnings,
    }
    specialist_results = dict(state.get("specialist_results") or {})
    specialist_results["sql"] = result
    return {
        "specialist_results": specialist_results,
        "evidence": list(state.get("evidence") or []) + evidence,
        "refusal_topic": state.get("refusal_topic") or refusal_topic,
        "logs": _append_log(state, {"node": "sql_specialist", "queries": all_queries, "status": status}),
    }


def rag_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    subtasks = _subtasks_for(state, "rag")
    if not subtasks:
        return {}
    from fahmai.tools.doc_tool import search_docs

    search_queries: list[str] = []
    vector_results: list[dict[str, Any]] = []
    keyword_results: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    terms = state.get("normalized_entities", {}).get("search_keywords") or []
    status = "no_data"
    refusal_topic: str | None = None
    for st in subtasks:
        task = str(st.get("task") or state.get("safe_underlying_question") or "")
        variants = list(dict.fromkeys([*terms[:5], task]))
        for idx, query in enumerate(variants[:6]):
            if not query:
                continue
            search_queries.append(query)
            keyword = query if idx < 5 else None
            raw = search_docs(query, keyword=keyword, k=ENTERPRISE_TOP_K)
            bucket = {"query": query, "result": raw}
            if keyword:
                keyword_results.append(bucket)
            else:
                vector_results.append(bucket)
            if raw and not raw.startswith(("SEARCH ERROR:", "(no matching documents)")):
                status = "success"
                evidence.append(
                    {
                        "source": "markdown" if keyword else "vector",
                        "doc_id": "search_result",
                        "chunk_id": query,
                        "claim": task,
                        "quote_or_snippet": raw[:1200],
                    }
                )
            elif raw.startswith("SEARCH ERROR:"):
                status = "error"
                warnings.append(raw)
        if status == "no_data":
            refusal_topic = refusal_topic or task
    result: SpecialistResult = {
        "status": status,
        "search_queries": search_queries,
        "vector_results": vector_results,
        "keyword_results": keyword_results,
        "summary": "Document evidence found." if evidence else "No document evidence found.",
        "evidence": evidence,
        "refusal_topic": refusal_topic,
        "warnings": warnings,
    }
    specialist_results = dict(state.get("specialist_results") or {})
    specialist_results["rag"] = result
    return {
        "specialist_results": specialist_results,
        "evidence": list(state.get("evidence") or []) + evidence,
        "refusal_topic": state.get("refusal_topic") or refusal_topic,
        "logs": _append_log(state, {"node": "rag_specialist", "search_queries": search_queries, "status": status}),
    }


def finance_compute_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    subtasks = _subtasks_for(state, "finance_compute")
    if not subtasks:
        return {}
    payload = _llm_json(
        COMPUTE_SYS,
        str(
            {
                "question": state.get("safe_underlying_question"),
                "subtasks": subtasks,
                "specialist_results": state.get("specialist_results", {}),
            }
        ),
    )
    if payload.get("_error") or not payload:
        payload = {
            "status": "missing_input",
            "inputs_used": [],
            "calculations": [],
            "summary": "Required verified numeric inputs are missing.",
            "evidence": [],
            "refusal_topic": state.get("safe_underlying_question"),
            "warnings": [payload.get("_error", "compute returned no JSON") if payload else "compute returned no JSON"],
        }
    result: SpecialistResult = {
        "status": str(payload.get("status") or "missing_input"),
        "summary": str(payload.get("summary") or ""),
        "evidence": list(payload.get("evidence") or []),
        "refusal_topic": payload.get("refusal_topic"),
        "warnings": list(payload.get("warnings") or []),
    }
    result["rows"] = [{"inputs_used": payload.get("inputs_used", []), "calculations": payload.get("calculations", [])}]
    specialist_results = dict(state.get("specialist_results") or {})
    specialist_results["finance_compute"] = result
    return {
        "specialist_results": specialist_results,
        "evidence": list(state.get("evidence") or []) + result.get("evidence", []),
        "refusal_topic": state.get("refusal_topic") or result.get("refusal_topic"),
        "logs": _append_log(state, {"node": "finance_compute", "status": result["status"]}),
    }


def refusal_specialist_node(state: EnterpriseState) -> dict[str, Any]:
    needs_refusal = bool(state.get("validation", {}).get("should_refuse")) or bool(_subtasks_for(state, "refusal"))
    if not needs_refusal:
        return {}
    validation = state.get("validation") or {}
    rtype = validation.get("refusal_type") or ("prompt_injection" if state.get("is_prompt_injection") else "data_not_found")
    topic = validation.get("refusal_topic") or state.get("refusal_topic") or state.get("safe_underlying_question") or "requested topic"
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
        "logs": _append_log(state, {"node": "refusal_specialist", "refusal_type": rtype, "topic": topic}),
    }


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
            refusal_topic = res.get("refusal_topic") if res else refusal_topic
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
            str(state.get("validation", {}).get("refusal_topic") or state.get("refusal_topic") or "requested topic"),
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
    answer = remove_forced_strings(answer, state.get("injection_reasons", []))
    if state.get("validation", {}).get("should_refuse") and not is_wellformed_refusal(answer):
        answer = refusal_answer(
            str(state.get("validation", {}).get("refusal_topic") or state.get("refusal_topic") or "requested topic"),
            state.get("language", "en"),
            "schema_missing" if state.get("validation", {}).get("refusal_type") == "schema_missing" else "data_not_found",
        )
    return {
        "final_answer": answer,
        "logs": _append_log(state, {"node": "output_formatter", "answer_len": len(answer)}),
    }
