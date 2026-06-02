# -*- coding: utf-8 -*-
"""SQL analyst sub-agent: text-to-SQL over the warehouse."""
from __future__ import annotations

from fahmai.agents.config import SQL_RECURSION
from fahmai.agents.prompts import SQL_SYS
from fahmai.agents.specialists.base import build_react
from fahmai.agents.tools import sql_query_tool

KIND = "sql"
RECURSION = SQL_RECURSION   # allow multi-step queries


def build():
    return build_react(SQL_SYS, [sql_query_tool])
