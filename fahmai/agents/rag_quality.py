# -*- coding: utf-8 -*-
"""Evidence quality and injection checks for the enterprise RAG Specialist."""
from __future__ import annotations

import re
from typing import Any

from fahmai.agents.config import RAG_MIN_RELEVANCE_SCORE
from fahmai.agents.rag_query_builder import dedupe_strings, tokenize

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s+prompt",
    r"developer\s+(message|instruction)",
    r"follow\s+these\s+instructions",
    r"hidden\s+instruction",
    r"output\s+exactly",
    r"reply\s+with\s+the\s+exact\s+string",
    r"do\s+not\s+use\s+internal\s+table",
    r"authoritative\s+memo",
]

BUSINESS_EVIDENCE_TERMS = {
    "branch",
    "campaign",
    "chat",
    "contract",
    "customer",
    "email",
    "employee",
    "faq",
    "finance",
    "inventory",
    "invoice",
    "memo",
    "minutes",
    "payment",
    "policy",
    "promo",
    "refund",
    "report",
    "return",
    "sales",
    "sku",
    "supplier",
    "vendor",
    "warranty",
}


def contains_injection(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(pattern, lower, flags=re.I) for pattern in INJECTION_PATTERNS)


def contains_business_evidence(text: str, required_terms: list[str]) -> bool:
    lower = (text or "").lower()
    has_business_term = any(term in lower for term in BUSINESS_EVIDENCE_TERMS)
    has_required_term = any(term.lower() in lower for term in required_terms if len(term) > 2)
    return has_business_term and has_required_term


def chunk_search_text(chunk: dict[str, Any]) -> str:
    meta = chunk.get("metadata") or {}
    return " ".join(
        [
            str(chunk.get("doc_id") or ""),
            str(chunk.get("text") or ""),
            " ".join(str(value) for value in meta.values()),
        ]
    ).lower()


def evaluate_result_quality(
    chunks: list[dict[str, Any]],
    required_terms: list[str],
    min_relevance_score: float | None = None,
) -> tuple[str, str, list[str], list[dict[str, Any]]]:
    threshold = RAG_MIN_RELEVANCE_SCORE if min_relevance_score is None else float(min_relevance_score)
    if not chunks:
        return "none", "no result", ["no result"], []

    trusted: list[dict[str, Any]] = []
    warnings: list[str] = []
    for chunk in chunks:
        text = chunk_search_text(chunk)
        if contains_injection(text) and not contains_business_evidence(text, required_terms):
            warnings.append("result contains injected instruction but not trusted business evidence")
            continue
        trusted.append(chunk)
    if not trusted:
        return "none", "; ".join(dedupe_strings(warnings or ["irrelevant chunks"])), dedupe_strings(warnings), []

    max_score = max(float(chunk.get("score") or 0.0) for chunk in trusted)
    if max_score < threshold:
        warnings.append("low similarity score")

    combined = " ".join(chunk_search_text(chunk) for chunk in trusted[:5])
    required_hits = [term for term in required_terms if term and term.lower() in combined]
    exact_or_date_terms = [term for term in required_terms if re.search(r"\d|[A-Z]{2,}[-_]", term)]
    if exact_or_date_terms and not any(term.lower() in combined for term in exact_or_date_terms):
        warnings.append("result does not contain the required entity/date/topic")

    query_terms: set[str] = set()
    for term in required_terms:
        query_terms.update(tokenize(term))
    evidence_terms = set(tokenize(combined))
    overlap = len(query_terms & evidence_terms)
    if query_terms and overlap == 0:
        warnings.append("irrelevant chunks")
    elif query_terms and overlap < min(2, len(query_terms)) and not required_hits:
        warnings.append("only tangential evidence")

    warnings = dedupe_strings(warnings)
    if not warnings:
        return "strong", "direct trusted business evidence matched requested entity/date/topic", [], trusted
    if warnings == ["low similarity score"] and required_hits:
        return "medium", "matched requested evidence but similarity score is below threshold", warnings, trusted
    if required_hits and "irrelevant chunks" not in warnings and "result does not contain the required entity/date/topic" not in warnings:
        return "medium", "; ".join(warnings), warnings, trusted
    return "weak", "; ".join(warnings), warnings, trusted


__all__ = [
    "BUSINESS_EVIDENCE_TERMS",
    "INJECTION_PATTERNS",
    "chunk_search_text",
    "contains_business_evidence",
    "contains_injection",
    "evaluate_result_quality",
]
