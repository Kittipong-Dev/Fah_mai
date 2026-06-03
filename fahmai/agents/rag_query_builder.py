# -*- coding: utf-8 -*-
"""Retry query generation for the enterprise RAG Specialist."""
from __future__ import annotations

import re
from typing import Any

from fahmai.agents.config import RAG_MAX_RETRIES

RETRY_STRATEGY_ORDER = [
    "exact_id_search",
    "entity_name_alias_search",
    "broader_concept_date_search",
    "thai_english_translation_variant",
    "abbreviation_expanded_name_variant",
    "remove_overly_specific_terms",
    "add_date_campaign_vendor_sku_context",
]

ABBREVIATION_EXPANSIONS = {
    "CEO": "chief executive officer",
    "CFO": "chief financial officer",
    "COO": "chief operating officer",
    "DQ": "data quality",
    "FIN": "finance",
    "FIN_CLOSE": "financial close",
    "INV": "invoice",
    "L1": "level one",
    "L2": "level two",
    "OPS": "operations",
    "OPS_REPORT": "operations report",
    "PM": "product memo",
    "Q1": "first quarter",
    "Q2": "second quarter",
    "Q3": "third quarter",
    "Q4": "fourth quarter",
    "SKU": "stock keeping unit",
}

QUERY_INJECTION_PATTERNS = [
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


def bounded_max_retries(value: Any = None) -> int:
    try:
        configured = int(value if value is not None else RAG_MAX_RETRIES)
    except (TypeError, ValueError):
        configured = RAG_MAX_RETRIES
    return max(1, min(configured, len(RETRY_STRATEGY_ORDER)))


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def dedupe_strings(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = " ".join(str(item).split())
        key = clean.lower()
        if clean and key not in seen:
            out.append(clean)
            seen.add(key)
    return out


def tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[_/]+", " ", text or "")
    raw = re.findall(r"[A-Za-z0-9-]+|[\u0e00-\u0e7f]+", normalized)
    stop = {
        "about",
        "answer",
        "business",
        "could",
        "evidence",
        "find",
        "from",
        "need",
        "record",
        "records",
        "related",
        "search",
        "that",
        "this",
        "what",
        "when",
        "where",
        "which",
        "with",
    }
    tokens: list[str] = []
    for token in raw:
        clean = token.strip("-").lower()
        if len(clean) > 2 and clean not in stop:
            tokens.append(clean)
    return dedupe_strings(tokens)


def extract_exact_ids(text: str) -> list[str]:
    patterns = [
        r"\b(?:SKU[-_])?[A-Z][A-Za-z0-9]*-[A-Za-z0-9]+-[A-Za-z0-9]+(?:-\d{3,4})?\b",
        r"\b(?:V|EMP|CUST|CUS|CRM)-[A-Z0-9-]+\d{3,}\b",
        r"\b(?:CAMP|CMP|PROMO|SF|POL|THREAD|CHAT|LINE|MSG|INV|INVOICE|MEMO|MIN|EMAIL)-[A-Z0-9-]+\b",
        r"\b[A-Z]{2,}(?:[_-][A-Z0-9]+){1,}\b",
    ]
    ids: list[str] = []
    for pattern in patterns:
        ids.extend(re.findall(pattern, text or "", flags=re.I))
    return dedupe_strings(ids)


def extract_dates(text: str) -> list[str]:
    dates: list[str] = []
    for pattern in (r"\b20\d{2}-\d{2}-\d{2}\b", r"\b20\d{2}\b", r"\bQ[1-4]\s*20\d{2}\b"):
        dates.extend(re.findall(pattern, text or "", flags=re.I))
    return dedupe_strings(dates)


def date_terms(date_constraints: dict[str, Any] | None) -> list[str]:
    if not date_constraints:
        return []
    terms: list[str] = []
    for item in date_constraints.get("dates") or []:
        terms.append(str(item))
    for item in date_constraints.get("years") or []:
        if isinstance(item, dict) and item.get("ce"):
            terms.append(str(item["ce"]))
    for item in date_constraints.get("quarters") or []:
        if isinstance(item, dict) and item.get("year") and item.get("quarter"):
            terms.append(f"{item['year']} Q{item['quarter']}")
    return dedupe_strings(terms)


def date_range_terms(date_range: Any) -> list[str]:
    if not isinstance(date_range, dict):
        return []
    terms: list[str] = []
    for value in date_range.values():
        if isinstance(value, list):
            terms.extend(str(item) for item in value if item)
        elif value:
            terms.append(str(value))
    return dedupe_strings(terms)


def hint_terms(retrieval_hints: dict[str, Any] | None) -> list[str]:
    hints = retrieval_hints or {}
    terms: list[str] = []
    for key in ("exact_ids", "primary_terms", "aliases", "document_types", "business_concepts"):
        terms.extend(as_list(hints.get(key)))
    terms.extend(date_range_terms(hints.get("date_range")))
    return dedupe_strings(terms)


def merge_retrieval_hints(
    subtask: dict[str, Any],
    state: dict[str, Any],
    task: str,
) -> dict[str, Any]:
    hints = dict(subtask.get("retrieval_hints") or {})
    entities = state.get("normalized_entities") or {}
    if "exact_ids" not in hints:
        exact_ids: list[str] = []
        for key in (
            "sku_ids",
            "vendor_ids",
            "employee_ids",
            "customer_ids",
            "campaign_ids",
            "policy_ids",
            "thread_ids",
            "invoice_ids",
        ):
            exact_ids.extend(as_list(entities.get(key)))
        exact_ids.extend(extract_exact_ids(task))
        if exact_ids:
            hints["exact_ids"] = dedupe_strings(exact_ids)
    if "primary_terms" not in hints:
        hints["primary_terms"] = as_list(entities.get("search_keywords"))[:8]
    if "aliases" not in hints and entities.get("aliases"):
        hints["aliases"] = as_list(entities.get("aliases"))
    if "date_range" not in hints:
        dates = date_terms(state.get("date_constraints") or {})
        if dates:
            hints["date_range"] = {"terms": dates}
    return hints


def required_terms(task: str, retrieval_hints: dict[str, Any], date_constraints: dict[str, Any] | None) -> list[str]:
    terms: list[str] = []
    terms.extend(as_list(retrieval_hints.get("exact_ids")))
    terms.extend(as_list(retrieval_hints.get("primary_terms"))[:5])
    terms.extend(as_list(retrieval_hints.get("aliases"))[:5])
    terms.extend(date_terms(date_constraints))
    terms.extend(extract_exact_ids(task))
    terms.extend(extract_dates(task))
    if not terms:
        terms.extend(tokenize(task)[:8])
    return dedupe_strings(terms)


def expand_abbreviations(query: str) -> str:
    expanded = query
    for abbr, full_name in ABBREVIATION_EXPANSIONS.items():
        if re.search(rf"\b{re.escape(abbr)}\b", query, flags=re.I):
            expanded += f" {full_name}"
    return " ".join(expanded.split())


def strip_injection_phrases(text: str) -> str:
    clean = text or ""
    for pattern in QUERY_INJECTION_PATTERNS:
        clean = re.sub(pattern, " ", clean, flags=re.I)
    return re.sub(r"\s{2,}", " ", clean).strip()


def build_retry_queries(task: str, retrieval_hints: dict[str, Any] | None = None, max_retries: Any = None) -> list[dict[str, str]]:
    max_attempts = bounded_max_retries(max_retries)
    hints = retrieval_hints or {}
    exact_ids = as_list(hints.get("exact_ids")) + extract_exact_ids(task)
    primary_terms = as_list(hints.get("primary_terms"))
    aliases = as_list(hints.get("aliases"))
    hint_text = " ".join(hint_terms(hints))
    dates = extract_dates(" ".join([task, hint_text]))
    dates.extend(date_range_terms(hints.get("date_range")))
    keywords = dedupe_strings(primary_terms + aliases + tokenize(task)[:8])
    broad_terms = [term for term in keywords if not re.search(r"\d", term)][:6]
    base_query = " ".join([task, hint_text]).strip()
    safe_base = strip_injection_phrases(base_query) or base_query

    candidates = [
        ("exact_id_search", " ".join(dedupe_strings(exact_ids)) or safe_base),
        ("entity_name_alias_search", " ".join(dedupe_strings(primary_terms + aliases + exact_ids)) or safe_base),
        ("broader_concept_date_search", " ".join(dedupe_strings(broad_terms + dates)) or safe_base),
        ("thai_english_translation_variant", f"{safe_base} Thai English terminology"),
        ("abbreviation_expanded_name_variant", expand_abbreviations(safe_base)),
        ("remove_overly_specific_terms", " ".join(broad_terms) or safe_base),
        ("add_date_campaign_vendor_sku_context", f"{safe_base} {' '.join(dates)} campaign vendor SKU context"),
    ]

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for strategy, query in candidates:
        clean = " ".join(str(query).split())
        key = clean.lower()
        if clean and key not in seen:
            out.append({"retry_strategy": strategy, "query": clean})
            seen.add(key)
        if len(out) >= max_attempts:
            return out

    filler_terms = dedupe_strings(exact_ids + primary_terms + aliases + broad_terms + [safe_base])
    for idx, term in enumerate(filler_terms, start=1):
        clean = " ".join([term, "document evidence", str(idx)]).strip()
        key = clean.lower()
        if clean and key not in seen:
            strategy = RETRY_STRATEGY_ORDER[len(out) % len(RETRY_STRATEGY_ORDER)]
            out.append({"retry_strategy": strategy, "query": clean})
            seen.add(key)
        if len(out) >= max_attempts:
            break
    return out[:max_attempts]


def keyword_for_query(query: str, retrieval_hints: dict[str, Any], terms: list[str]) -> str | None:
    candidates = (
        as_list(retrieval_hints.get("exact_ids"))
        + extract_exact_ids(query)
        + as_list(retrieval_hints.get("primary_terms"))
        + as_list(retrieval_hints.get("aliases"))
        + terms
        + tokenize(query)
    )
    for candidate in dedupe_strings(candidates):
        if 2 <= len(candidate) <= 80:
            return candidate
    return None


__all__ = [
    "RETRY_STRATEGY_ORDER",
    "as_list",
    "bounded_max_retries",
    "build_retry_queries",
    "dedupe_strings",
    "extract_dates",
    "extract_exact_ids",
    "keyword_for_query",
    "merge_retrieval_hints",
    "required_terms",
    "tokenize",
]
