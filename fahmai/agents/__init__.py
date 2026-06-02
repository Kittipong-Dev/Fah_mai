# -*- coding: utf-8 -*-
"""FahMai team agent — a LangGraph multi-agent that answers the L3 questions.

    from fahmai.agents import aanswer, answer, QMAP
    print(answer(QMAP["L3-Q-EASY-001"]))

Layout:
    config.py        env + constants            llm.py          model factory
    prompts/         one system prompt per role tools/          LangChain tool wrappers
    specialists/     one sub-agent per module   utils/          json/dedup/scoring helpers
    graph.py         the team graph + aanswer   data.py         questions / ground-truth loaders
    runner.py        batch -> submission.csv    evaluate.py     regression compare vs ground-truth
"""
from fahmai.agents import config  # noqa: F401  (side effect: load .env + enable LangSmith FIRST)
from fahmai.agents.data import QMAP, load_ground_truth, load_questions
from fahmai.agents.graph import aanswer, answer, build_team

__all__ = ["aanswer", "answer", "build_team", "QMAP", "load_questions", "load_ground_truth"]
