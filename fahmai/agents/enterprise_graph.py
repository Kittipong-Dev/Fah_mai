# -*- coding: utf-8 -*-
"""Enterprise LangGraph pipeline for FahMai data QA."""
from __future__ import annotations

import asyncio

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from fahmai.agents.config import TEAM_RECURSION
from fahmai.agents.enterprise_nodes import (
    aggregate_specialist_outputs_node,
    answer_checker_node,
    evidence_validator_node,
    finance_compute_specialist_node,
    final_analyzer_node,
    language_guard_node,
    llm_injection_guardrail_node,
    output_formatter_hook,
    planned_worker_groups,
    planner_json_validation_hook,
    planner_node,
    question_classifier_node,
    question_intake_node,
    question_normalizer_node,
    refusal_specialist_node,
    route_specialist_coverage,
    rule_based_injection_guardrail_node,
    specialist_coverage_node,
    specialist_worker_node,
)
from fahmai.agents.enterprise_state import EnterpriseState

_TEAM = None


def dispatch_specialists(state: EnterpriseState):
    groups = planned_worker_groups(state)
    if not groups:
        return "specialist_coverage"
    attempt = int(state.get("replan_attempts") or 0)
    return [
        Send(
            "specialist_worker",
            {
                **state,
                "active_specialist": specialist,
                "active_subtasks": subtasks,
                "active_attempt": attempt,
            },
        )
        for specialist, subtasks in groups.items()
    ]


def build_enterprise_team():
    g = StateGraph(EnterpriseState)
    g.add_node("question_intake", question_intake_node)
    g.add_node("question_normalizer", question_normalizer_node)
    g.add_node("rule_based_injection_guardrail", rule_based_injection_guardrail_node)
    g.add_node("llm_injection_guardrail", llm_injection_guardrail_node)
    g.add_node("question_classifier", question_classifier_node)
    g.add_node("planner", planner_node)
    g.add_node("planner_json_validation", planner_json_validation_hook)
    g.add_node("specialist_worker", specialist_worker_node)
    g.add_node("aggregate_specialist_outputs", aggregate_specialist_outputs_node)
    g.add_node("finance_compute_specialist", finance_compute_specialist_node)
    g.add_node("specialist_coverage", specialist_coverage_node)
    g.add_node("evidence_validator", evidence_validator_node)
    g.add_node("refusal_specialist", refusal_specialist_node)
    g.add_node("final_analyzer", final_analyzer_node)
    g.add_node("language_guard", language_guard_node)
    g.add_node("answer_checker", answer_checker_node)
    g.add_node("output_formatter", output_formatter_hook)

    g.add_edge(START, "question_intake")
    g.add_edge("question_intake", "question_normalizer")
    g.add_edge("question_normalizer", "rule_based_injection_guardrail")
    g.add_edge("rule_based_injection_guardrail", "llm_injection_guardrail")
    g.add_edge("llm_injection_guardrail", "question_classifier")
    g.add_edge("question_classifier", "planner")
    g.add_edge("planner", "planner_json_validation")
    g.add_conditional_edges(
        "planner_json_validation",
        dispatch_specialists,
        ["specialist_worker", "specialist_coverage"],
    )
    g.add_edge("specialist_worker", "aggregate_specialist_outputs")
    g.add_edge("aggregate_specialist_outputs", "specialist_coverage")
    g.add_edge("finance_compute_specialist", "specialist_coverage")
    g.add_conditional_edges(
        "specialist_coverage",
        route_specialist_coverage,
        {
            "planner_json_validation": "planner_json_validation",
            "finance_compute_specialist": "finance_compute_specialist",
            "evidence_validator": "evidence_validator",
        },
    )
    g.add_edge("evidence_validator", "refusal_specialist")
    g.add_edge("refusal_specialist", "final_analyzer")
    g.add_edge("final_analyzer", "language_guard")
    g.add_edge("language_guard", "answer_checker")
    g.add_edge("answer_checker", "output_formatter")
    g.add_edge("output_formatter", END)
    return g.compile()


def get_enterprise_team():
    global _TEAM
    if _TEAM is None:
        _TEAM = build_enterprise_team()
    return _TEAM


async def aanswer(question: str) -> str:
    out = await get_enterprise_team().ainvoke(
        {
            "raw_question": question,
            "specialist_results": {},
            "evidence": [],
            "logs": [],
            "worker_outputs": [],
            "replan_attempts": 0,
        },
        config={"recursion_limit": TEAM_RECURSION},
    )
    return out.get("final_answer") or "(no answer)"


def answer(question: str) -> str:
    return asyncio.run(aanswer(question))


def build_team():
    return build_enterprise_team()
