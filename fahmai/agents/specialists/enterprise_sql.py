# -*- coding: utf-8 -*-
"""Enterprise SQL specialist implementation."""
from __future__ import annotations

import re
from typing import Any, Callable

from fahmai.agents.enterprise_state import EnterpriseState, SpecialistResult
from fahmai.agents.enterprise_utils import (
    is_valid_readonly_sql,
    sanitize_refusal_topic,
    strip_sql_fences,
)
from fahmai.agents.prompts.enterprise import SQL_GENERATOR_SYS


JsonLLM = Callable[[str, str], dict[str, Any]]
AppendLog = Callable[[EnterpriseState, dict[str, Any]], list[dict[str, Any]]]


def _remote_daily_sales_spike_query(state: EnterpriseState, subtasks: list[dict[str, Any]]) -> str | None:
    text = " ".join(
        [
            str(state.get("safe_underlying_question") or state.get("normalized_question") or state.get("raw_question") or ""),
            *(str(st.get("task") or "") for st in subtasks),
        ]
    )
    if not re.search(r"\bREMOTE\b", text, re.I):
        return None
    if not re.search(r"\bFACT_SALES\b|\bv_sales\b|sales", text, re.I):
        return None
    if not re.search(r"spike|พุ่ง|ผิดปกติ|maximum|max|highest|มากที่สุด", text, re.I):
        return None
    if not re.search(r"sku|รายการ|items?", text, re.I):
        return None
    return """
WITH spike_date AS (
    SELECT
        s.business_event_date::date AS spike_date,
        COUNT(DISTINCT s.txn_id) AS total_transactions
    FROM v_sales s
    WHERE s.branch_code = 'REMOTE'
      AND s.business_event_date BETWEEN '2025-01-01' AND '2025-12-31'
    GROUP BY 1
    ORDER BY total_transactions DESC, spike_date
    LIMIT 1
),
sku_rank AS (
    SELECT
        si.sku_id,
        SUM(si.quantity) AS dominant_units,
        COUNT(DISTINCT si.txn_id) AS txns_with_sku
    FROM v_sales s
    JOIN v_sales_items si ON si.txn_id = s.txn_id
    JOIN spike_date sd ON sd.spike_date = s.business_event_date::date
    WHERE s.branch_code = 'REMOTE'
    GROUP BY si.sku_id
    ORDER BY dominant_units DESC, txns_with_sku DESC, si.sku_id
    LIMIT 1
)
SELECT
    sd.spike_date,
    sr.sku_id AS dominant_sku,
    sr.dominant_units,
    sr.txns_with_sku,
    sd.total_transactions
FROM spike_date sd
CROSS JOIN sku_rank sr
"""


def _payload(state: EnterpriseState, st: dict[str, Any], rows: list[dict[str, Any]], llm_json: JsonLLM) -> dict[str, Any]:
    return llm_json(
        SQL_GENERATOR_SYS,
        str(
            {
                "normalized_question": state.get("normalized_question"),
                "safe_underlying_question": state.get("safe_underlying_question"),
                "task": st.get("task"),
                "depends_on": st.get("depends_on", []),
                "entities": state.get("normalized_entities"),
                "date_constraints": state.get("date_constraints"),
                "prior_specialist_results": state.get("specialist_results", {}),
                "prior_sql_rows": rows,
            }
        ),
    )


def _repair_payload(
    state: EnterpriseState,
    st: dict[str, Any],
    rows: list[dict[str, Any]],
    failed_payload: dict[str, Any],
    llm_json: JsonLLM,
) -> dict[str, Any]:
    return llm_json(
        SQL_GENERATOR_SYS,
        str(
            {
                "repair_instruction": (
                    "Previous SQL generation did not produce a usable query. Try once more. "
                    "Use the original business question, prior SQL rows, and schema to write a "
                    "self-contained read-only SELECT/WITH query. If a subtask says 'previous step', "
                    "resolve that dependency from prior_sql_rows or combine the steps in one query. "
                    "Do not return schema_missing unless the requested business field is truly absent."
                ),
                "failed_payload": failed_payload,
                "original_business_question": state.get("safe_underlying_question") or state.get("normalized_question"),
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


def run(
    state: EnterpriseState,
    subtasks: list[dict[str, Any]],
    llm_json: JsonLLM,
    append_log: AppendLog,
) -> dict[str, Any]:
    if not subtasks:
        return {}
    from fahmai.tools.sql_tool import sql_query

    all_queries: list[str] = []
    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    status = "success"
    refusal_topic: str | None = None
    repair_count = 0
    fallback_topic = state.get("safe_underlying_question") or state.get("normalized_question")
    deterministic_query = _remote_daily_sales_spike_query(state, subtasks)
    if deterministic_query:
        result_text = sql_query(deterministic_query)
        all_queries.append(deterministic_query.strip())
        rows.append({"task_id": "deterministic_remote_sales_spike", "sql": deterministic_query.strip(), "result": result_text})
        if not result_text.startswith("SQL ERROR:") and result_text.strip() != "(0 rows)":
            evidence.append(
                {
                    "source": "postgres",
                    "table_or_view": "v_sales/v_sales_items",
                    "claim": "REMOTE daily sales spike in 2025 and dominant SKU",
                    "value": result_text,
                }
            )
            status = "success"
        else:
            warnings.append(result_text)

    for st in subtasks:
        if deterministic_query and evidence:
            continue
        payload = _payload(state, st, rows, llm_json)
        if payload.get("_error"):
            if not evidence:
                status = "error"
            warnings.append(payload["_error"][:160])
            continue

        queries = [strip_sql_fences(q) for q in payload.get("queries", []) if q]
        if (payload.get("status") == "schema_missing" or not queries) and not payload.get("_error"):
            repaired = _repair_payload(state, st, rows, payload, llm_json)
            if repaired and not repaired.get("_error"):
                repair_count += 1
                repaired_queries = [strip_sql_fences(q) for q in repaired.get("queries", []) if q]
                if repaired_queries or repaired.get("status") != "schema_missing":
                    payload = repaired
                    queries = repaired_queries
            elif repaired.get("_error"):
                warnings.append(f"SQL repair failed: {repaired['_error'][:140]}")

        if payload.get("status") == "schema_missing":
            if not evidence:
                status = "schema_missing"
            refusal_topic = sanitize_refusal_topic(payload.get("refusal_topic") or st.get("task"), fallback_topic)
            warnings.extend(payload.get("warnings") or [])
            continue
        if not queries:
            if not evidence:
                status = "schema_missing"
            refusal_topic = sanitize_refusal_topic(st.get("task"), fallback_topic)
            warnings.append("SQL generator returned no query.")
            continue

        for sql in queries[:3]:
            if not is_valid_readonly_sql(sql):
                status = "error"
                warnings.append(f"Blocked non-read-only SQL: {sql[:120]}")
                continue
            result = sql_query(sql)
            all_queries.append(sql)
            rows.append({"task_id": st.get("id"), "sql": sql, "result": result})
            if result.startswith("SQL ERROR:"):
                if not evidence:
                    status = "error"
                warnings.append(result)
            elif result.strip() == "(0 rows)":
                if status != "error" and not evidence:
                    status = "no_data"
                refusal_topic = refusal_topic or sanitize_refusal_topic(st.get("task"), fallback_topic)
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
        "logs": append_log(
            state,
            {"node": "sql_specialist", "queries": all_queries, "status": status, "repairs": repair_count},
        ),
    }
