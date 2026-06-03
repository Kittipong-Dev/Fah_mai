# -*- coding: utf-8 -*-
"""RAG researcher sub-agent: vector search over pgvector rag_chunks (chat documents)."""
from __future__ import annotations

from fahmai.agents.config import DOC_RECURSION
from fahmai.agents.prompts.rag import RAG_SYS
from fahmai.agents.specialists.base import build_react
from fahmai.agents.tools.rag_search import rag_search_tool

KIND = "rag"
RECURSION = DOC_RECURSION


def build():
    return build_react(RAG_SYS, [rag_search_tool])
