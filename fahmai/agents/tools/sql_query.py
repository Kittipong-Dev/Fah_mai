# -*- coding: utf-8 -*-
"""sql_query_tool — one read-only SELECT/WITH over the FahMai warehouse."""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.tools.sql_tool import sql_query


@tool
def sql_query_tool(sql: str) -> str:
    """Run ONE read-only SELECT/WITH query over the FahMai Postgres warehouse; returns a markdown
    table (truncated). Prefer the curated v_* views. If you get 'SQL ERROR: ...', fix the SQL and
    try again."""
    return sql_query(sql)
