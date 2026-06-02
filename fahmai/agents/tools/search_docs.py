# -*- coding: utf-8 -*-
"""search_docs_tool — semantic doc search, capped to DOC_K DISTINCT snippets (FIX #3).

Over-fetches from the low-level retriever, then `dedup_blocks` drops near-identical synthetic
chat variants so the agent sees a few distinct documents instead of 8 copies of the same boilerplate.
"""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.agents.config import DOC_K
from fahmai.utils.dedup import dedup_blocks
from fahmai.tools.doc_tool import search_docs


@tool
def search_docs_tool(query: str, channel: str = "", topic: str = "", date_from: str = "",
                     date_to: str = "", keyword: str = "", k: int = 0) -> str:
    """Semantic search over documents. Pre-filter with channel
    (chat_oa, chat_works, email, memo, minutes, kb_policy, kb_product, store_info, report),
    topic (event tag e.g. DQ3-2025-04-05, DQ4, CEO, E2, E3, L1), date_from/date_to (YYYY-MM-DD),
    or exact keyword (invoice id / SKU). Returns a few DISTINCT doc snippets (near-duplicates are
    collapsed)."""
    keep = k or DOC_K
    # over-fetch so dedup still leaves `keep` distinct results
    raw = search_docs(query, channel=channel or None, topic=topic or None,
                      date_from=date_from or None, date_to=date_to or None,
                      keyword=keyword or None, k=max(keep * 5, 15))
    return dedup_blocks(raw, keep=keep)
