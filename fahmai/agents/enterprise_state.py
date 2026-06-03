# -*- coding: utf-8 -*-
"""Stable JSON-like state contracts for the enterprise data-agent graph."""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

Language = Literal["th", "en", "mixed"]
QuestionType = Literal[
    "simple_sql_lookup",
    "sql_aggregation",
    "sql_join",
    "sql_anomaly_detection",
    "multi_table_reconciliation",
    "document_lookup",
    "hybrid_sql_rag",
    "finance_compute",
    "refusal_expected",
    "prompt_injection",
    "schema_field_missing",
    "unknown",
]
Specialist = Literal["sql", "rag", "finance_compute", "refusal"]


class PlanSubtask(TypedDict, total=False):
    id: str
    specialist: Specialist
    task: str
    depends_on: list[str]
    required: bool
    expected_output: str


class Plan(TypedDict, total=False):
    goal: str
    subtasks: list[PlanSubtask]
    final_answer_requirements: list[str]
    risk_flags: list[str]


class Evidence(TypedDict, total=False):
    source: str
    table_or_view: str
    doc_id: str
    chunk_id: str
    claim: str
    value: Any
    quote_or_snippet: str


class SpecialistResult(TypedDict, total=False):
    status: str
    queries: list[str]
    search_queries: list[str]
    vector_results: list[dict[str, Any]]
    keyword_results: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    summary: str
    evidence: list[Evidence]
    refusal_topic: str | None
    warnings: list[str]


class Validation(TypedDict, total=False):
    is_supported: bool
    unsupported_claims: list[str]
    missing_required_evidence: list[str]
    should_refuse: bool
    refusal_type: Literal["data_not_found", "schema_missing", "prompt_injection"] | None
    refusal_topic: str | None
    confidence: Literal["high", "medium", "low"]


class EnterpriseState(TypedDict, total=False):
    raw_question: str
    language: Language
    normalized_question: str
    normalized_entities: dict[str, Any]
    date_constraints: dict[str, Any]
    question_type: QuestionType
    is_prompt_injection: bool
    injection_reasons: list[str]
    safe_underlying_question: str
    plan: Plan
    specialist_results: dict[str, SpecialistResult]
    evidence: list[Evidence]
    answer_candidate: str
    validation: Validation
    final_answer: str
    refusal_topic: str | None
    errors: list[str]
    logs: list[dict[str, Any]]
    failed_subtasks: list[PlanSubtask]
    replan_attempts: int
    worker_outputs: Annotated[list[dict[str, Any]], operator.add]
    active_specialist: Specialist
    active_subtasks: list[PlanSubtask]
    active_attempt: int
