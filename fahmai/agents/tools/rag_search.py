# -*- coding: utf-8 -*-
"""rag_search_tool — hybrid search over rag_chunks (pgvector DB).

Supports all source types in rag_chunks:
  chat_line_oa       — customer LINE OA chats
  chat_line_works    — internal LINE WORKS team chats
  pos_log            — POS terminal transaction logs (BKK-CTW and others)
  web_log            — web session / e-commerce event logs
  l1_kb              — product knowledge base (FAQs, specs, pricing)
  ops_monthly_report — monthly ops summaries (revenue, per-branch, returns, inventory)
  fin_quarterly_close— quarterly financial close reports (cash flow, AR, opex)
  email              — internal/external emails
  memo               — internal memos
  minutes            — meeting minutes

Strategy:
  1. Embed query with Qwen3-Embedding-8B (4096-d) for vector similarity.
  2. Apply metadata filters as WHERE clauses.
  3. Falls back to keyword-only (ILIKE on contextualized_content) if embed fails.
"""
from __future__ import annotations

from langchain_core.tools import tool
from sqlalchemy import text

import os

from fahmai.embed import rag_embed_batch
from fahmai.rag_db import RAG_ENGINE

SNIPPET = 500
_RAG_DIM = int(os.getenv("RAG_EMBED_DIM", "1024"))


def _vec(query: str) -> list[float] | None:
    try:
        v = rag_embed_batch([query])[0]
        return v if len(v) == _RAG_DIM else None
    except Exception:  # noqa: BLE001
        return None


def _fmt_vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.5f}" for x in v) + "]"


def _match_official(vec: list[float], k: int) -> str | None:
    """Official retrieval contract: fah_sai_lpk_rag.match_public_chunks_bge_m3 (parent-child BGE-M3).
    Returns hydrated parent_text + source_table/source_pk for citation. None on error."""
    try:
        with RAG_ENGINE.connect() as c:
            rows = c.execute(text("""
                SELECT source_table, source_pk, source_path, similarity,
                       left(parent_text, 700) AS parent_text, left(chunk_text, 300) AS chunk_text
                FROM fah_sai_lpk_rag.match_public_chunks_bge_m3(cast(:q AS vector(1024)), :k, 80)
            """), {"q": _fmt_vec(vec), "k": int(k)}).fetchall()
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return "(no matching chunks)"
    out = []
    for r in rows:
        cite = f" src={r.source_table}/{r.source_pk}" if r.source_table else (f" path={r.source_path}" if r.source_path else "")
        txt = " ".join((r.parent_text or r.chunk_text or "").split())
        out.append(f"[{r.similarity:.3f}]{cite}\n    {txt}")
    return "\n".join(out)


def search_rag(
    query: str,
    source_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    keyword: str | None = None,
    branch_code: str | None = None,
    sku_id: str | None = None,
    period: str | None = None,
    quarter: str | None = None,
    report_family: str | None = None,
    metric_group: str | None = None,
    record_id: str | None = None,
    k: int = 5,
) -> str:
    # No targeted filters -> use the official BGE-M3 parent-child retrieval function (the contract).
    has_filter = any([source_type, date_from, date_to, keyword, branch_code, sku_id,
                      period, quarter, report_family, metric_group, record_id])
    if not has_filter:
        vec0 = _vec(query)
        if vec0:
            res = _match_official(vec0, k)
            if res is not None:
                return res
        # else fall through to keyword fallback below

    where, params = [], {"k": int(k)}

    if source_type:
        where.append("metadata->>'source_type' = :src")
        params["src"] = source_type
    if date_from:
        where.append("metadata->>'event_date' >= :df")
        params["df"] = date_from
    if date_to:
        where.append("metadata->>'event_date' <= :dt")
        params["dt"] = date_to
    if branch_code:
        where.append("metadata->>'branch_code' = :bc")
        params["bc"] = branch_code
    if sku_id:
        where.append("(metadata->>'sku_id' = :sku OR metadata @> jsonb_build_object('sku_ids', jsonb_build_array(:sku)))")
        params["sku"] = sku_id
    if period:
        where.append("metadata->>'period' = :period")
        params["period"] = period
    if quarter:
        where.append("metadata->>'quarter' = :quarter")
        params["quarter"] = quarter
    if report_family:
        where.append("metadata->>'report_family' = :rf")
        params["rf"] = report_family
    if metric_group:
        where.append("metadata->>'metric_group' = :mg")
        params["mg"] = metric_group
    if record_id:
        where.append("metadata->>'record_id' = :rid")
        params["rid"] = record_id
    if keyword:
        where.append("contextualized_content ILIKE :kw")
        params["kw"] = f"%{keyword}%"

    clause = ("WHERE " + " AND ".join(where)) if where else ""

    vec = _vec(query)
    if vec:
        params["q"] = _fmt_vec(vec)
        sql = f"""
            SELECT chunk_id,
                   metadata->>'source_type'  AS source_type,
                   metadata->>'record_id'    AS record_id,
                   metadata->>'event_date'   AS event_date,
                   metadata->>'period'       AS period,
                   metadata->>'metric_group' AS metric_group,
                   1 - (embedding <=> cast(:q AS vector)) AS sim,
                   left(contextualized_content, {SNIPPET}) AS snippet
            FROM rag_chunks
            {clause}
            ORDER BY embedding <=> cast(:q AS vector)
            LIMIT :k
        """
    else:
        if not where:
            where.append("contextualized_content ILIKE :fallback_kw")
            params["fallback_kw"] = f"%{query[:80]}%"
            clause = "WHERE " + " AND ".join(where)
        sql = f"""
            SELECT chunk_id,
                   metadata->>'source_type'  AS source_type,
                   metadata->>'record_id'    AS record_id,
                   metadata->>'event_date'   AS event_date,
                   metadata->>'period'       AS period,
                   metadata->>'metric_group' AS metric_group,
                   NULL AS sim,
                   left(contextualized_content, {SNIPPET}) AS snippet
            FROM rag_chunks
            {clause}
            LIMIT :k
        """

    try:
        with RAG_ENGINE.connect() as c:
            rows = c.execute(text(sql), params).fetchall()
    except Exception as e:  # noqa: BLE001
        return f"RAG SEARCH ERROR: {str(e).splitlines()[0]}"

    if not rows:
        return "(no matching chunks)"

    out = []
    for r in rows:
        sim_tag = f"[{r.sim:.3f}]" if r.sim is not None else "[kw]"
        extra = ""
        if r.period:
            extra += f" period={r.period}"
        if r.metric_group:
            extra += f" mg={r.metric_group}"
        snip = " ".join((r.snippet or "").split())
        out.append(
            f"{sim_tag} {r.chunk_id} ({r.source_type}, date={r.event_date},{extra} id={r.record_id})\n    {snip}"
        )
    return "\n".join(out)


@tool
def rag_search_tool(
    query: str,
    source_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    keyword: str | None = None,
    branch_code: str | None = None,
    sku_id: str | None = None,
    period: str | None = None,
    quarter: str | None = None,
    report_family: str | None = None,
    metric_group: str | None = None,
    record_id: str | None = None,
    k: int = 5,
) -> str:
    """Search the RAG chunk database (pgvector, Qwen3-Embedding-8B, 4096-d).

    Source types:
      chat_line_oa       — customer LINE OA chats
      chat_line_works    — internal LINE WORKS team chats
      pos_log            — POS terminal logs (branch_code, txn_id, sku_ids)
      web_log            — web/e-commerce session logs
      l1_kb              — product KB (sku_id, price_thb, brand, status)
      ops_monthly_report — monthly ops summaries; filter by period='YYYY-MM', metric_group
      fin_quarterly_close— quarterly fin close; filter by period='YYYY-QN', quarter='Q1'..'Q4'
      email / memo / minutes — written documents

    Metadata filters (use to narrow results):
      source_type   — one of the types above
      date_from/to  — ISO date range on event_date
      branch_code   — e.g. 'BKK-CTW', 'HKT-FEST'
      sku_id        — e.g. 'NT-LT-001'
      period        — 'YYYY-MM' for monthly, 'YYYY-QN' for quarterly (e.g. '2025-04', '2025-Q2')
      quarter       — 'Q1'..'Q4' (fin_quarterly_close only)
      report_family — 'ops' or 'fin'
      metric_group  — e.g. 'revenue_summary', 'per_branch_performance', 'returns_warranty',
                       'top_skus_by_revenue', 'inventory_health', 'cs_interaction_volume',
                       'cash_flow', 'ar_aging', 'operating_expense', 'revenue_split'
      record_id     — direct lookup by document record ID
      keyword       — exact substring (ILIKE) on chunk content
    """
    return search_rag(
        query=query, source_type=source_type,
        date_from=date_from, date_to=date_to, keyword=keyword,
        branch_code=branch_code, sku_id=sku_id,
        period=period, quarter=quarter, report_family=report_family,
        metric_group=metric_group, record_id=record_id, k=k,
    )
