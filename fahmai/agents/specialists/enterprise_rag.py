# -*- coding: utf-8 -*-
"""Enterprise RAG specialist implementation."""
from __future__ import annotations

from typing import Any, Callable

from fahmai.agents.config import ENTERPRISE_TOP_K
from fahmai.agents.enterprise_state import EnterpriseState, SpecialistResult

AppendLog = Callable[[EnterpriseState, dict[str, Any]], list[dict[str, Any]]]


def run(
    state: EnterpriseState,
    subtasks: list[dict[str, Any]],
    append_log: AppendLog,
) -> dict[str, Any]:
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
        "logs": append_log(state, {"node": "rag_specialist", "search_queries": search_queries, "status": status}),
    }
