# -*- coding: utf-8 -*-
"""LangChain @tool wrappers over the low-level fahmai.tools.* functions."""
from fahmai.agents.tools.get_document import get_document_tool
from fahmai.agents.tools.search_docs import search_docs_tool
from fahmai.agents.tools.sql_query import sql_query_tool

ALL_TOOLS = [sql_query_tool, search_docs_tool, get_document_tool]

__all__ = ["sql_query_tool", "search_docs_tool", "get_document_tool", "ALL_TOOLS"]
