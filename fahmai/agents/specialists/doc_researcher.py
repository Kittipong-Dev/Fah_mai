# -*- coding: utf-8 -*-
"""Document researcher sub-agent: narrative retrieval over the doc corpus."""
from __future__ import annotations

from fahmai.agents.config import DOC_RECURSION
from fahmai.agents.prompts import DOC_SYS
from fahmai.agents.specialists.base import build_react
from fahmai.agents.tools import get_document_tool, search_docs_tool

KIND = "doc"
RECURSION = DOC_RECURSION   # cap ~tool calls (anti-loop)


def build():
    return build_react(DOC_SYS, [search_docs_tool, get_document_tool])
