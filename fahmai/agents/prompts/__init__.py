# -*- coding: utf-8 -*-
"""System prompts for every role in the team. One prompt per module.

(verify.py is retired — verification moved to the data-layer `coverage` gate in graph.py.)
"""
from fahmai.agents.prompts.doc import DOC_SYS
from fahmai.agents.prompts.planner import PLANNER_SYS
from fahmai.agents.prompts.sql import SQL_SYS
from fahmai.agents.prompts.synth import SYNTH_SYS

__all__ = ["PLANNER_SYS", "SQL_SYS", "DOC_SYS", "SYNTH_SYS"]
