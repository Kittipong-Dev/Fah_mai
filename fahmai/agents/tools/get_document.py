# -*- coding: utf-8 -*-
"""get_document_tool — full text of one document by id."""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.tools.doc_tool import get_document


@tool
def get_document_tool(doc_id: str) -> str:
    """Return the FULL text of one document by doc_id (to extract an exact phrase / amount)."""
    return get_document(doc_id)
