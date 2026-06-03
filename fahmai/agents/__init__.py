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
try:
    from fahmai.agents.enterprise_graph import aanswer, answer, build_team
except ModuleNotFoundError as _import_error:  # pragma: no cover - bare helper imports without deps
    _GRAPH_IMPORT_ERROR = _import_error

    def build_team():
        raise _GRAPH_IMPORT_ERROR

    async def aanswer(_question: str) -> str:
        raise _GRAPH_IMPORT_ERROR

    def answer(_question: str) -> str:
        raise _GRAPH_IMPORT_ERROR

__all__ = ["aanswer", "answer", "build_team", "QMAP", "load_questions", "load_ground_truth"]
