# -*- coding: utf-8 -*-
"""System prompts for every role in the team. One prompt per module.

(verify.py is retired — verification moved to the data-layer `coverage` gate in graph.py.)
"""
from fahmai.agents.prompts.classify import CLASSIFY_SYS
from fahmai.agents.prompts.compute import COMPUTE_SYS
from fahmai.agents.prompts.doc import DOC_SYS
from fahmai.agents.prompts.planner import PLANNER_SYS
from fahmai.agents.prompts.rag import RAG_SYS
from fahmai.agents.prompts.sql import SQL_SYS
from fahmai.agents.prompts.sql_verify import SQL_VERIFY_SYS
from fahmai.agents.prompts.synth import SYNTH_SYS

__all__ = ["CLASSIFY_SYS", "COMPUTE_SYS", "PLANNER_SYS", "SQL_SYS", "SQL_VERIFY_SYS",
           "DOC_SYS", "RAG_SYS", "SYNTH_SYS"]
