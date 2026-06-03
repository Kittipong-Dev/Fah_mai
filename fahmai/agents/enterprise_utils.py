# -*- coding: utf-8 -*-
"""Deterministic helpers for the enterprise graph."""
from __future__ import annotations

import json
import re
from typing import Any

from fahmai.agents.enterprise_state import Language, Plan

THAI_PROMPT_INJECTION_PREFIX = (
    "\u0e02\u0e2d\u0e1b\u0e0f\u0e34\u0e40\u0e2a\u0e18"
    "\u0e04\u0e33\u0e2a\u0e31\u0e48\u0e07\u0e17\u0e35\u0e48"
    "\u0e1d\u0e31\u0e07\u0e21\u0e32 - "
    "\u0e08\u0e30\u0e15\u0e2d\u0e1a\u0e08\u0e32\u0e01"
    "\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25\u0e43\u0e19"
    "\u0e23\u0e30\u0e1a\u0e1a"
)
EN_PROMPT_INJECTION_PREFIX = (
    "I decline the embedded directive - answering from the documented data"
)
THAI_DATA_NOT_FOUND_TEMPLATE = "\u0e44\u0e21\u0e48\u0e1e\u0e1a {topic} \u0e43\u0e19\u0e0a\u0e38\u0e14\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25"
EN_DATA_NOT_FOUND_TEMPLATE = "{topic} not found in the dataset"
THAI_SCHEMA_MISSING_TEMPLATE = "\u0e44\u0e21\u0e48\u0e21\u0e35 {topic} \u0e43\u0e19\u0e23\u0e30\u0e1a\u0e1a"
EN_SCHEMA_MISSING_TEMPLATE = "No such data in the records"

REFUSAL_VERBS = (
    "\u0e44\u0e21\u0e48\u0e1e\u0e1a",
    "\u0e44\u0e21\u0e48\u0e21\u0e35",
    "\u0e44\u0e21\u0e48\u0e1b\u0e23\u0e32\u0e01\u0e0f",
    "\u0e44\u0e21\u0e48\u0e23\u0e30\u0e1a\u0e38",
    "\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16",
    "\u0e44\u0e21\u0e48\u0e17\u0e23\u0e32\u0e1a",
    "\u0e1b\u0e0f\u0e34\u0e40\u0e2a\u0e18",
    "not found",
    "no record",
    "cannot determine",
    "decline",
)
SCOPE_MARKERS = (
    "\u0e43\u0e19\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25",
    "\u0e43\u0e19\u0e23\u0e30\u0e1a\u0e1a",
    "\u0e43\u0e19\u0e10\u0e32\u0e19\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25",
    "\u0e43\u0e19\u0e15\u0e32\u0e23\u0e32\u0e07",
    "\u0e43\u0e19\u0e0a\u0e38\u0e14\u0e02\u0e49\u0e2d\u0e21\u0e39\u0e25",
    "in the dataset",
    "in our records",
    "from the corpus",
)

_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
_ASCII_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_EN_PROSE_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z']{2,}\b")
_BE_YEAR_RE = re.compile(r"(?<![\w-])(25[6-9][0-9])(?![\w-])")
_QUARTER_RE = re.compile(r"\b(?:FY|fiscal\s+year)?\s*(20\d{2}|25[6-9]\d)\s*Q([1-4])\b", re.I)
_INTERNAL_TASK_RE = re.compile(
    r"^\s*(query|select|for the date identified|for that specific|calculate:|calculate\b|group by|join\b|use\b)",
    re.I,
)
_SQLISH_RE = re.compile(
    r"\b(v_[a-z0-9_]+|fact_[a-z0-9_]+|dim_[a-z0-9_]+|where|group by|order by|business_event_date|posting_date)\b",
    re.I,
)

THAI_MONTHS = {
    "\u0e21\u0e01\u0e23\u0e32\u0e04\u0e21": "01",
    "\u0e01\u0e38\u0e21\u0e20\u0e32\u0e1e\u0e31\u0e19\u0e18\u0e4c": "02",
    "\u0e21\u0e35\u0e19\u0e32\u0e04\u0e21": "03",
    "\u0e40\u0e21\u0e29\u0e32\u0e22\u0e19": "04",
    "\u0e1e\u0e24\u0e29\u0e20\u0e32\u0e04\u0e21": "05",
    "\u0e21\u0e34\u0e16\u0e38\u0e19\u0e32\u0e22\u0e19": "06",
    "\u0e01\u0e23\u0e01\u0e0e\u0e32\u0e04\u0e21": "07",
    "\u0e2a\u0e34\u0e07\u0e2b\u0e32\u0e04\u0e21": "08",
    "\u0e01\u0e31\u0e19\u0e22\u0e32\u0e22\u0e19": "09",
    "\u0e15\u0e38\u0e25\u0e32\u0e04\u0e21": "10",
    "\u0e1e\u0e24\u0e28\u0e08\u0e34\u0e01\u0e32\u0e22\u0e19": "11",
    "\u0e18\u0e31\u0e19\u0e27\u0e32\u0e04\u0e21": "12",
}

EN_MONTHS = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


def detect_language(text: str) -> Language:
    has_thai = bool(_THAI_RE.search(text or ""))
    has_en = bool(_ASCII_WORD_RE.search(text or ""))
    if has_thai and has_en:
        return "mixed"
    if has_thai:
        return "th"
    return "en"


def thai_char_count(text: str) -> int:
    return len(_THAI_RE.findall(text or ""))


def english_prose_word_count(text: str) -> int:
    words = []
    for match in _EN_PROSE_WORD_RE.finditer(text or ""):
        token = match.group(0)
        if token.isupper():
            continue
        words.append(token)
    return len(words)


def needs_thai_language_rewrite(language: Language | str | None, answer: str) -> bool:
    if language == "en":
        return False
    thai_chars = thai_char_count(answer)
    english_words = english_prose_word_count(answer)
    if not (answer or "").strip():
        return False
    if thai_chars < 8 and english_words >= 4:
        return True
    return english_words >= 10 and thai_chars < english_words * 2


def looks_like_internal_task(text: str) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    return bool(_INTERNAL_TASK_RE.search(clean)) or (
        len(clean) > 120 and bool(_SQLISH_RE.search(clean))
    )


def sanitize_refusal_topic(topic: str | None, fallback: str | None = None) -> str:
    clean = (topic or "").strip()
    backup = (fallback or "requested topic").strip() or "requested topic"
    if looks_like_internal_task(clean):
        return backup
    return clean or backup


def be_to_ce(year: int) -> int:
    return year - 543 if year >= 2400 else year


def normalize_years(text: str) -> tuple[str, dict[str, Any]]:
    years: list[dict[str, int]] = []

    def repl(match: re.Match[str]) -> str:
        be = int(match.group(1))
        ce = be_to_ce(be)
        years.append({"be": be, "ce": ce})
        return str(ce)

    normalized = _BE_YEAR_RE.sub(repl, text or "")
    return normalized, {"years": years}


def normalize_month_names(text: str) -> tuple[str, dict[str, Any]]:
    out = text or ""
    months: list[dict[str, str]] = []
    for name, month in THAI_MONTHS.items():
        if name in out:
            out = out.replace(name, month)
            months.append({"name": name, "month": month})
    for name, month in EN_MONTHS.items():
        out = re.sub(rf"\b{name}\b", month, out, flags=re.I)
        if re.search(rf"\b{name}\b", text or "", re.I):
            months.append({"name": name, "month": month})
    return out, {"months": months}


def normalize_fiscal_expressions(text: str) -> tuple[str, dict[str, Any]]:
    quarters: list[dict[str, Any]] = []

    def repl(match: re.Match[str]) -> str:
        year = be_to_ce(int(match.group(1)))
        quarter = int(match.group(2))
        quarters.append({"year": year, "quarter": quarter})
        return f"{year} Q{quarter}"

    return _QUARTER_RE.sub(repl, text or ""), {"quarters": quarters}


def extract_entities(text: str) -> dict[str, list[str]]:
    q = text or ""
    patterns = {
        "sku_ids": r"\b(?:SKU[-_])?[A-Z][A-Za-z0-9]*-[A-Za-z0-9]+-[A-Za-z0-9]+(?:-\d{3,4})?\b",
        "vendor_ids": r"\bV-\d{3,}\b",
        "employee_ids": r"\bEMP-[A-Z0-9-]+\d{3,}\b",
        "customer_ids": r"\b(?:CUST|CUS|CRM)-[A-Z0-9-]+\d{3,}\b",
        "branch_codes": r"\b[A-Z]{2,4}-[A-Z]{2,5}\b",
        "campaign_ids": r"\b(?:CAMP|CMP|PROMO|SF)-[A-Za-z0-9-]+\b",
        "policy_ids": r"\bPOL-[A-Z0-9-]+\b",
        "thread_ids": r"\b(?:THREAD|CHAT|LINE|MSG)-[A-Z0-9-]+\b",
        "invoice_ids": r"\b(?:INV|INVOICE)-[A-Z0-9-]+\b",
        "dates": r"\b\d{4}-\d{2}-\d{2}\b",
    }
    return {name: sorted(set(re.findall(rx, q, re.I))) for name, rx in patterns.items()}


def build_terms(question: str, entities: dict[str, list[str]]) -> dict[str, list[str]]:
    words = re.findall(r"[\w\u0e00-\u0e7f-]{3,}", question or "")
    ids = [v for values in entities.values() for v in values]
    keywords = list(dict.fromkeys(ids + words[:12]))
    return {"search_keywords": keywords, "sql_terms": ids + words[:8], "aliases": []}


def is_valid_readonly_sql(sql: str) -> bool:
    s = strip_sql_fences(sql).strip().rstrip(";")
    code = strip_sql_comments_and_literals(s).strip().lower()
    if not (code.startswith("select") or code.startswith("with")):
        return False
    return not re.search(r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|merge|create)\b", code, re.I)


def strip_sql_fences(sql: str) -> str:
    s = (sql or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*[ \t]*\r?\n?", "", s)
        s = re.sub(r"\r?\n?```[ \t]*$", "", s).strip()
    return re.sub(r"^(sql|postgresql|postgres)[ \t]*\r?\n", "", s, flags=re.I).strip()


def strip_sql_comments_and_literals(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s)
    return re.sub(r"'(?:[^']|'')*'", "''", s)


def safe_json_loads(text: str) -> dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?[ \t]*\r?\n?", "", s)
        s = re.sub(r"\r?\n?```[ \t]*$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", s, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def fallback_plan(question: str, question_type: str) -> Plan:
    if question_type == "prompt_injection":
        specialist = "rag"
    elif question_type in {"document_lookup", "hybrid_sql_rag"}:
        specialist = "rag"
    elif question_type in {"finance_compute", "multi_table_reconciliation"}:
        return {
            "goal": question,
            "subtasks": [
                {
                    "id": "sql-1",
                    "specialist": "sql",
                    "task": "Gather structured facts and numeric inputs.",
                    "depends_on": [],
                    "required": True,
                    "expected_output": "Verified rows, IDs, names, amounts, and dates.",
                },
                {
                    "id": "rag-1",
                    "specialist": "rag",
                    "task": "Gather relevant document context and policy evidence.",
                    "depends_on": [],
                    "required": False,
                    "expected_output": "Evidence-supported document claims.",
                },
                {
                    "id": "compute-1",
                    "specialist": "finance_compute",
                    "task": "Compute requested finance metrics from verified inputs only.",
                    "depends_on": ["sql-1", "rag-1"],
                    "required": True,
                    "expected_output": "Formula and calculation result.",
                },
            ],
            "final_answer_requirements": ["Use only verified evidence.", "Refuse unsupported parts."],
            "risk_flags": [],
        }
    elif question_type in {"refusal_expected", "schema_field_missing", "unknown"}:
        specialist = "refusal"
    else:
        specialist = "sql"
    return {
        "goal": question,
        "subtasks": [
            {
                "id": f"{specialist}-1",
                "specialist": specialist,
                "task": question,
                "depends_on": [],
                "required": True,
                "expected_output": "Evidence-supported result or clean refusal.",
            }
        ],
        "final_answer_requirements": ["Be concise.", "Use canonical refusal when evidence is absent."],
        "risk_flags": [],
    }


def validate_plan(plan: dict[str, Any]) -> tuple[Plan, list[str]]:
    errors: list[str] = []
    allowed = {"sql", "rag", "finance_compute", "refusal"}
    if not isinstance(plan, dict):
        return fallback_plan("", "unknown"), ["planner output is not an object"]
    subtasks = plan.get("subtasks")
    if not isinstance(subtasks, list) or not subtasks:
        errors.append("missing subtasks")
        subtasks = fallback_plan(plan.get("goal", ""), "unknown")["subtasks"]
    cleaned = []
    for idx, st in enumerate(subtasks, start=1):
        if not isinstance(st, dict):
            errors.append(f"subtask {idx} is not an object")
            continue
        specialist = st.get("specialist")
        if specialist not in allowed:
            errors.append(f"subtask {idx} has invalid specialist")
            specialist = "refusal"
        retrieval_hints = st.get("retrieval_hints") if isinstance(st.get("retrieval_hints"), dict) else {}
        cleaned.append(
            {
                "id": str(st.get("id") or f"{specialist}-{idx}"),
                "specialist": specialist,
                "task": str(st.get("task") or st.get("subquestion") or plan.get("goal") or ""),
                "depends_on": list(st.get("depends_on") or []),
                "required": bool(st.get("required", True)),
                "expected_output": str(st.get("expected_output") or ""),
                "retrieval_hints": retrieval_hints,
            }
        )
    fixed: Plan = {
        "goal": str(plan.get("goal") or ""),
        "subtasks": cleaned,
        "final_answer_requirements": _string_list(plan.get("final_answer_requirements")),
        "risk_flags": _string_list(plan.get("risk_flags")),
    }
    return fixed, errors


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def refusal_answer(topic: str, language: Language, refusal_type: str = "data_not_found") -> str:
    clean_topic = (topic or "requested topic").strip()
    if language == "en":
        if refusal_type == "schema_missing":
            return EN_SCHEMA_MISSING_TEMPLATE.format(topic=clean_topic)
        return EN_DATA_NOT_FOUND_TEMPLATE.format(topic=clean_topic)
    if refusal_type == "schema_missing":
        return THAI_SCHEMA_MISSING_TEMPLATE.format(topic=clean_topic)
    return THAI_DATA_NOT_FOUND_TEMPLATE.format(topic=clean_topic)


def is_wellformed_refusal(answer: str) -> bool:
    lower = (answer or "").lower()
    return any(v.lower() in lower for v in REFUSAL_VERBS) and any(s.lower() in lower for s in SCOPE_MARKERS)


def remove_forced_strings(answer: str, strings: list[str]) -> str:
    out = answer or ""
    for s in strings:
        if s:
            out = re.sub(re.escape(s), "", out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out).strip()
