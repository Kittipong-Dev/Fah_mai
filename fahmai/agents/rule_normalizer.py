# -*- coding: utf-8 -*-
"""ASCII-safe rule-based normalization hints for enterprise questions.

This module intentionally uses only the stable, deterministic parts of the
teammate rule normalizer: IDs, English aliases, date windows, and routing hints.
Downloaded Thai literals in that artifact were mojibake, so they are not copied
here.
"""
from __future__ import annotations

import calendar
import json
import re
from typing import Any


TABLE_ALIASES = {
    "sales": "v_sales",
    "sale": "v_sales",
    "basket": "v_sales",
    "line item": "v_sales_items",
    "line items": "v_sales_items",
    "sales line": "v_sales_items",
    "sku revenue": "v_sales_items",
    "units sold": "v_sales_items",
    "bank transaction": "FACT_BANK_TRANSACTION",
    "bank transactions": "FACT_BANK_TRANSACTION",
    "vendor payment": "FACT_VENDOR_PAYMENT",
    "vendor payments": "FACT_VENDOR_PAYMENT",
    "shipping": "FACT_SHIPPING",
    "shipment": "FACT_SHIPPING",
    "cs interaction": "FACT_CS_INTERACTION",
    "inventory snapshot": "v_inventory_snapshot",
    "inventory movement": "FACT_INVENTORY_MOVEMENT",
    "return": "v_returns",
    "returns": "v_returns",
    "refund": "FACT_REFUND_PAID",
    "refunds": "FACT_REFUND_PAID",
    "warranty claim": "FACT_WARRANTY_CLAIM",
    "warranty claims": "FACT_WARRANTY_CLAIM",
    "claim": "FACT_WARRANTY_CLAIM",
    "promo redemption": "FACT_PROMO_REDEMPTION",
    "redemption": "FACT_PROMO_REDEMPTION",
    "loyalty": "FACT_LOYALTY_LEDGER",
    "points": "DIM_POLICY_VERSION",
    "payroll": "FACT_PAYROLL",
    "product": "DIM_PRODUCT",
    "product family": "DIM_PRODUCT",
    "msrp": "DIM_PRODUCT",
    "vendor": "DIM_VENDOR",
    "branch": "DIM_BRANCH",
    "customer": "DIM_CUSTOMER",
    "employee": "DIM_EMPLOYEE",
    "approver": "DIM_EMPLOYEE",
    "department": "DIM_DEPARTMENT",
    "policy": "DIM_POLICY_VERSION",
    "contract": "DIM_VENDOR_CONTRACT_VERSION",
    "campaign": "DIM_PROMO_CAMPAIGN",
    "bank account": "DIM_BANK_ACCOUNT",
    "signing authority": "dim_signing_authority_ladder",
    "recall history": "dim_product_recall_history",
    "promo mechanic": "dim_promo_mechanic",
}

ENTITY_ALIASES = {
    "Powercell X3": ("product_aliases", "NT-LT-001", "Powercell X3"),
    "NovaTech Powercell X3": ("product_aliases", "NT-LT-001", "NovaTech Powercell X3"),
    "NovaTech laptop": ("product_aliases", "NT-LT-001", "NovaTech laptop"),
    "SF-Galaxy-Pro-2568": ("sku_ids", "SF-Galaxy-Pro-2568", "SF-Galaxy-Pro-2568"),
    "E5 flagship": ("product_aliases", "SF-Galaxy-Pro-2568", "E5 flagship"),
    "SaiFah flagship": ("product_aliases", "SF-Galaxy-Pro-2568", "SaiFah flagship"),
    "PayWise": ("vendor_aliases", "V-013", "PayWise"),
    "VeloShip": ("vendor_aliases", "V-006", "VeloShip"),
    "NovaTech": ("vendor_aliases", "V-002", "NovaTech"),
    "KBANK-OPER": ("account_ids", "KBANK-OPER", "KBANK-OPER"),
    "SF-LAUNCH-2568": ("campaign_ids", "SF-LAUNCH-2568", "SF-LAUNCH-2568"),
    "MEGA-1111-2567": ("campaign_ids", "MEGA-1111-2567", "MEGA-1111-2567"),
    "MEGA-1111-2568": ("campaign_ids", "MEGA-1111-2568", "MEGA-1111-2568"),
}

BRANCH_CODE_ALIASES = {
    "REMOTE": "REMOTE",
    "remote branch": "REMOTE",
    "REMOTE branch": "REMOTE",
    "online branch": "REMOTE",
    "e-commerce branch": "REMOTE",
}

DOC_FAMILIES = {
    "LINE WORKS": "docs/chat_line_works",
    "LINE Works": "docs/chat_line_works",
    "chat_line_works": "docs/chat_line_works",
    "LINE OA": "docs/chat_line_oa",
    "chat_line_oa": "docs/chat_line_oa",
    "memo": "docs/memo",
    "minutes": "docs/minutes",
    "email": "docs/email",
    "l1_kb": "docs/l1_kb",
    "KB": "docs/l1_kb",
    "reports": "reports",
    "report": "reports",
}

EVENT_ALIASES = {
    "duplicate invoice": "DQ3",
    "DQ3": "DQ3",
    "double-log": "DQ4",
    "double logging": "DQ4",
    "double-logging": "DQ4",
    "promo redemption": "DQ4",
    "DQ4": "DQ4",
    "stockout": "E3",
    "stock-out": "E3",
    "component shortage": "E3",
    "E3": "E3",
    "delivery delay": "E2",
    "shipment delay": "E2",
    "delayed shipment": "E2",
    "E2": "E2",
    "CEO": "CEO",
    "leadership transition": "CEO",
    "recall": "E9",
    "E9": "E9",
    "L1": "L1",
    "L2": "L2",
    "L3": "L3",
}

METRIC_ALIASES = {
    "count": ["count"],
    "sum": ["sum"],
    "total": ["sum"],
    "top": ["rank", "top_n"],
    "best-selling": ["rank", "max"],
    "top-selling": ["rank", "max"],
    "maximum": ["rank", "max"],
    "minimum": ["rank", "min"],
    "average": ["avg"],
    "ROI": ["roi"],
    "reconciliation": ["reconciliation"],
    "reconcile": ["reconciliation"],
    "dedup": ["deduplication"],
    "duplicate": ["deduplication"],
    "phantom": ["deduplication"],
    "transition": ["state_transition_lookup"],
    "recall_status": ["state_transition_lookup"],
    "cash outflow": ["cash_outflow"],
    "net cost": ["net_cost"],
    "MSRP": ["msrp_lookup"],
    "refund": ["refund_total_thb"],
    "return-rate": ["rate"],
    "growth": ["growth"],
    "YoY": ["growth"],
    "variance": ["variance"],
    "gap": ["gap"],
}

TABLE_RE = re.compile(r"\b(?:FACT|DIM)_[A-Z0-9_]+\b|\bdim_[a-z0-9_]+\b|\bv_[a-z0-9_]+\b|T2_DOC_INVENTORY", re.I)
SKU_RE = re.compile(r"\b(?:SKU-[A-Z0-9-]+|[A-Z]{2}-[A-Z]{2}-\d{3}|SF-Galaxy-Pro-2568)\b")
VENDOR_RE = re.compile(r"\bV-\d{3}\b")
EMPLOYEE_RE = re.compile(r"\bEMP-[A-Z0-9-]+\d{3,}\b")
CUSTOMER_RE = re.compile(r"\bCUST-[A-Z0-9-]+\b")
BRANCH_RE = re.compile(r"\b(?:BKK|CNX|HKT|UDN|REMOTE)[A-Z0-9-]*\b")
ACCOUNT_RE = re.compile(r"\b[A-Z]+-[A-Z]+\b")
INVOICE_RE = re.compile(r"\b[A-Z]{1,4}-INV-\d{4}-\d+\b|\bPW-INV-\d{4}-\d+\b|\bINV-[A-Z0-9-]+\b")
TXN_RE = re.compile(r"\bTXN-[A-Z0-9-]+\b")
RETURN_RE = re.compile(r"\bRET-[A-Z0-9-]+\b")
REFUND_RE = re.compile(r"\bRF-[A-Z0-9-]+\b")
CLAIM_RE = re.compile(r"\bWC-\d{6}-\d+\b")
ISO_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
ISO_MONTH_RE = re.compile(r"\b20\d{2}-\d{2}\b")
BE_YEAR_RE = re.compile(r"\b256[7-9]\b")
QUARTER_RE = re.compile(r"\bQ([1-4])(?:\s+calendar)?\s+(20\d{2}|256[7-9])\b", re.I)
FY_RE = re.compile(r"\bFY(20\d{2}|256[7-9])\b", re.I)
DATE_AXIS_COLUMNS = ("business_event_date", "posting_date", "effective_date", "as_of_date")


def _uniq(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            out.append(clean)
            seen.add(clean)
    return out


def _alias_in_text(alias: str, text: str, ignore_case: bool = True) -> bool:
    flags = re.I if ignore_case else 0
    if re.fullmatch(r"[A-Za-z0-9_ -]+", alias):
        pattern = rf"(?<![A-Za-z0-9_-]){re.escape(alias)}(?![A-Za-z0-9_-])"
        return bool(re.search(pattern, text or "", flags))
    return bool(re.search(re.escape(alias), text or "", flags))


def _to_ce(year: str) -> int:
    value = int(year)
    return value - 543 if value >= 2400 else value


def _normalize_table_name(raw: str) -> str:
    if raw.lower().startswith(("dim_", "v_")):
        return raw.lower()
    return raw.upper()


def _infer_date_type(text: str, span_start: int, span_end: int) -> tuple[str, str]:
    window = text[max(0, span_start - 90) : min(len(text), span_end + 90)].lower()
    if "posting" in window or "posted" in window:
        return "posting_date", "posting_window"
    if "effective" in window or "policy" in window:
        return "effective_date", "policy_as_of"
    if "as_of" in window or "snapshot" in window:
        return "as_of_date", "snapshot"
    if "timestamp" in window or "log" in window:
        return "timestamp", "event_timestamp"
    if "recall window" in window:
        return "business_event_date", "recall_window"
    return "business_event_date", "event_date"


def question_shape(qid: str, text: str) -> dict[str, Any]:
    difficulty = "unknown"
    for token in ("EASY", "MED", "HARD", "XHARD", "REF", "INJ"):
        if f"-{token}-" in qid:
            difficulty = token.lower()
            break
    part_nums = [int(x) for x in re.findall(r"\((\d+)\)", text or "")]
    expected = max(part_nums, default=0)
    is_multi = bool(expected >= 2 or re.search(r"5-tuple|tuple|both|all parts|part\s+\d", text or "", re.I))
    return {
        "is_multi_part": is_multi,
        "expected_answer_parts": expected if expected else None,
        "difficulty_hint": difficulty,
    }


def extract_rule_entities(text: str) -> tuple[dict[str, list[str]], list[dict[str, str]], list[str]]:
    entities: dict[str, list[str]] = {
        "sku_ids": SKU_RE.findall(text or ""),
        "product_aliases": [],
        "campaign_ids": [],
        "vendor_ids": VENDOR_RE.findall(text or ""),
        "vendor_aliases": [],
        "employee_ids": EMPLOYEE_RE.findall(text or ""),
        "employee_roles": [],
        "customer_ids": CUSTOMER_RE.findall(text or ""),
        "branch_codes": BRANCH_RE.findall(text or ""),
        "branch_filter_hints": [],
        "account_ids": ACCOUNT_RE.findall(text or ""),
        "invoice_ids": INVOICE_RE.findall(text or ""),
        "txn_ids": TXN_RE.findall(text or ""),
        "return_ids": RETURN_RE.findall(text or ""),
        "refund_ids": REFUND_RE.findall(text or ""),
        "claim_ids": CLAIM_RE.findall(text or ""),
        "event_codes": [],
        "aliases": [],
    }
    warnings: list[dict[str, str]] = []

    for raw, (kind, canonical, alias) in ENTITY_ALIASES.items():
        if not _alias_in_text(raw, text or ""):
            continue
        entities[kind].append(alias)
        entities["aliases"].append(alias)
        if kind == "product_aliases":
            entities["sku_ids"].append(canonical)
        elif kind == "vendor_aliases":
            entities["vendor_ids"].append(canonical)
            if raw == "NovaTech":
                warnings.append(
                    {
                        "type": "ambiguous_alias",
                        "value": raw,
                        "canonical_guess": canonical,
                        "reason": "NovaTech can be a product brand or vendor V-002; verify table context.",
                    }
                )
        elif kind in {"campaign_ids", "account_ids", "sku_ids"}:
            entities[kind].append(canonical)

    for raw, branch_code in BRANCH_CODE_ALIASES.items():
        if _alias_in_text(raw, text or ""):
            entities["branch_codes"].append(branch_code)
            entities["branch_filter_hints"].append(f"branch_code='{branch_code}'")
            entities["aliases"].append(raw)

    for raw, event in EVENT_ALIASES.items():
        if _alias_in_text(raw, text or ""):
            entities["event_codes"].append(event)

    for role in ("CEO", "CFO", "approver", "Incoming CEO", "Founder & CEO"):
        if re.search(re.escape(role), text or "", re.I):
            entities["employee_roles"].append(role)

    for key, values in list(entities.items()):
        entities[key] = _uniq(values)

    known_ids = {value for values in entities.values() for value in values}
    unresolved = []
    for token in re.findall(r"\b[A-Z]{2,}-[A-Z0-9-]+(?:-\d+)?\b", text or ""):
        if token not in known_ids and not token.startswith(("FACT_", "DIM_")):
            unresolved.append(token)
    return entities, warnings, _uniq(unresolved)


def extract_rule_dates(text: str) -> list[dict[str, Any]]:
    dates: list[dict[str, Any]] = []
    for match in QUARTER_RE.finditer(text or ""):
        quarter = int(match.group(1))
        year = _to_ce(match.group(2))
        start_month = 3 * (quarter - 1) + 1
        end_month = start_month + 2
        end_day = calendar.monthrange(year, end_month)[1]
        dates.append(
            {
                "raw": match.group(0),
                "start": f"{year}-{start_month:02d}-01",
                "end": f"{year}-{end_month:02d}-{end_day:02d}",
                "date_type": "business_event_date",
                "role_hint": "quarter",
            }
        )

    for match in FY_RE.finditer(text or ""):
        year = _to_ce(match.group(1))
        dates.append(
            {
                "raw": match.group(0),
                "start": f"{year}-01-01",
                "end": f"{year}-12-31",
                "date_type": "business_event_date",
                "role_hint": "fiscal_year",
            }
        )

    iso_dates = list(ISO_DATE_RE.finditer(text or ""))
    paired: set[int] = set()
    for index, match in enumerate(iso_dates):
        if index in paired:
            continue
        if index + 1 < len(iso_dates):
            nxt = iso_dates[index + 1]
            between = (text or "")[match.end() : nxt.start()]
            if re.search(r"\b(to|through|until|between|and)\b|-|\u2013|\u2014", between, re.I) and len(between) <= 40:
                date_type, role = _infer_date_type(text or "", match.start(), nxt.end())
                dates.append(
                    {
                        "raw": (text or "")[match.start() : nxt.end()],
                        "start": match.group(0),
                        "end": nxt.group(0),
                        "date_type": date_type,
                        "role_hint": role,
                    }
                )
                paired.update({index, index + 1})
                continue
        date_type, role = _infer_date_type(text or "", match.start(), match.end())
        dates.append(
            {
                "raw": match.group(0),
                "start": match.group(0),
                "end": match.group(0),
                "date_type": date_type,
                "role_hint": role,
            }
        )
        paired.add(index)

    for match in ISO_MONTH_RE.finditer(text or ""):
        if ISO_DATE_RE.match((text or "")[match.start() : match.start() + 10]):
            continue
        year, month = map(int, match.group(0).split("-"))
        end_day = calendar.monthrange(year, month)[1]
        dates.append(
            {
                "raw": match.group(0),
                "start": f"{year}-{month:02d}-01",
                "end": f"{year}-{month:02d}-{end_day:02d}",
                "date_type": "business_event_date",
                "role_hint": "month",
            }
        )

    for match in BE_YEAR_RE.finditer(text or ""):
        year = _to_ce(match.group(0))
        if any(str(year) in str(date.get("start")) for date in dates):
            continue
        dates.append(
            {
                "raw": match.group(0),
                "start": f"{year}-01-01",
                "end": f"{year}-12-31",
                "date_type": "business_event_date",
                "role_hint": "year",
            }
        )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for date in dates:
        key = json.dumps(date, sort_keys=True)
        if key not in seen:
            out.append(date)
            seen.add(key)
    return out


def infer_date_axis(text: str, dates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    q = text or ""
    explicit_columns = [column for column in DATE_AXIS_COLUMNS if re.search(rf"\b{column}\b", q, re.I)]
    if explicit_columns:
        default_axis = explicit_columns[0]
        reason = "question explicitly names the date column"
    elif dates:
        default_axis = "business_event_date"
        reason = (
            "period filters such as in year/month/quarter default to the business event axis; "
            "posting_date/effective_date/as_of_date are used only when explicitly requested"
        )
    else:
        default_axis = "business_event_date"
        reason = "default event-time axis for FACT_* business events"

    vendor_payment_period_warning = bool(
        dates
        and re.search(r"\b(vendor payment|vendor payments|FACT_VENDOR_PAYMENT|v_vendor_payments)\b", q, re.I)
        and "posting_date" not in explicit_columns
    )
    return {
        "default_axis": default_axis,
        "explicit_columns": explicit_columns,
        "date_columns": list(DATE_AXIS_COLUMNS),
        "vendor_payment_period_warning": vendor_payment_period_warning,
        "reason": reason,
    }


def extract_rule_sql_terms(text: str) -> dict[str, list[str]]:
    explicit = [_normalize_table_name(value) for value in TABLE_RE.findall(text or "")]
    table_hints = list(explicit)
    for alias, table in TABLE_ALIASES.items():
        if _alias_in_text(alias, text or ""):
            table_hints.append(table)

    column_hints = []
    for column in (
        "business_event_date",
        "posting_date",
        "effective_date",
        "as_of_date",
        "month_end_date",
        "closing_units",
        "txn_id",
        "sku_id",
        "vendor_id",
        "customer_id",
        "branch_code",
        "branch_type",
        "employee_id",
        "approved_by_employee_id",
        "campaign_id",
        "account_id",
        "return_reason",
        "claim_reason",
        "recall_status",
        "routing_destination",
        "net_total_thb",
        "basket_total_thb",
        "line_total_thb",
        "amount_thb",
        "refund_amount_thb",
        "return_amount_thb",
        "msrp_thb",
        "payment_status",
        "payment_method",
        "related_entity_table",
        "related_entity_id",
    ):
        if column in (text or ""):
            column_hints.append(column)

    metric_hints: list[str] = []
    operation_hints: list[str] = []
    operations = {"count", "sum", "avg", "rank", "max", "min", "deduplication", "reconciliation", "state_transition_lookup"}
    for alias, metrics in METRIC_ALIASES.items():
        if not _alias_in_text(alias, text or ""):
            continue
        for metric in metrics:
            if metric in operations:
                operation_hints.append(metric)
            else:
                metric_hints.append(metric)
    if extract_rule_dates(text):
        operation_hints.append("date_window_filter")

    return {
        "explicit_tables": _uniq(explicit),
        "table_hints": _uniq(table_hints),
        "column_hints": _uniq(column_hints),
        "metric_hints": _uniq(metric_hints),
        "operation_hints": _uniq(operation_hints),
    }


def extract_rule_rag_terms(text: str) -> dict[str, Any]:
    keywords: list[str] = []
    families: list[str] = []
    for raw, family in DOC_FAMILIES.items():
        if _alias_in_text(raw, text or ""):
            keywords.append(raw)
            families.append(family)
    claim_markers = re.findall(r"CLAIM\.[A-Z0-9_.-]+", text or "")
    requires = bool(
        families
        or re.search(r"\b(document|documents|evidence|thread|corpus|public/docs|memo|minutes|email|chat|faq)\b", text or "", re.I)
    )
    return {
        "requires_rag": requires,
        "rag_keywords": _uniq(keywords),
        "doc_families": _uniq(families),
        "event_markers": _uniq(claim_markers),
    }


def extract_rule_log_terms(text: str) -> dict[str, Any]:
    families: list[str] = []
    if re.search(r"pos_log_line_id|\.tsv|pos_\*|pos_[A-Z0-9-]+_\d{8}|public/logs", text or "", re.I):
        families.append("logs/pos")
    if re.search(r"web_log_line_id|\.jsonl|\bweb_\d{8}|web logs?", text or "", re.I):
        families.append("logs/web")
    if re.search(r"paywise_fee|fee_log", text or "", re.I):
        families.append("logs/paywise")
    if re.search(r"logs folder|public/logs|audit trail", text or "", re.I) and not families:
        families.append("logs/unknown_or_fact_log")
    line_hints = re.findall(r"[A-Za-z0-9_.-]+\.(?:tsv|jsonl):line\d+", text or "")
    return {
        "requires_logs": bool(families),
        "log_families": _uniq(families),
        "line_id_hints": _uniq(line_hints),
    }


def extract_rule_constraints(text: str, qid: str = "") -> tuple[dict[str, Any], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    dataset_only = bool(re.search(r"data lake|public data lake|public/|documented data|dataset|records", text or "", re.I))
    public_only = bool(re.search(r"public corpus|public/", text or "", re.I))
    no_external = bool(re.search(r"do not.*external|documented data|data lake", text or "", re.I))
    missing = bool(re.search(r"not found|unavailable|out[- ]of[- ]corpus|if there is no|if not present", text or "", re.I))
    injection = bool(re.search(r"\[SYSTEM\]|verbatim|Do NOT|ignore|Reply in English only|embedded directive|CONFIRMED_", text or "", re.I))
    if injection or "-INJ-" in qid:
        warnings.append({"type": "possible_prompt_injection", "action": "send_to_guardrail"})
    if missing or "-REF-" in qid:
        warnings.append({"type": "possible_refusal_case", "action": "preserve_topic_and_scope"})
    return (
        {
            "dataset_only": dataset_only,
            "public_only": public_only,
            "do_not_use_external_knowledge": no_external,
            "missing_data_instruction": missing,
            "must_verify_candidate_values": True,
        },
        warnings,
    )


def normalize_question_rule_based(text: str, qid: str = "") -> dict[str, Any]:
    entities, entity_warnings, unresolved = extract_rule_entities(text or "")
    dates = extract_rule_dates(text or "")
    date_axis = infer_date_axis(text or "", dates)
    sql_terms = extract_rule_sql_terms(text or "")
    rag_terms = extract_rule_rag_terms(text or "")
    log_terms = extract_rule_log_terms(text or "")
    constraints, constraint_warnings = extract_rule_constraints(text or "", qid)
    requires_sql = bool(sql_terms["explicit_tables"] or sql_terms["table_hints"])
    if not requires_sql and not rag_terms["requires_rag"] and not log_terms["requires_logs"] and "-REF-" not in qid:
        requires_sql = True
    if not sql_terms["table_hints"] and requires_sql:
        constraint_warnings.append({"type": "sql_required_but_no_table_hint", "action": "planner_uses_schema_card"})

    return {
        "question_id": qid,
        "normalized_question": (text or "").strip(),
        "question_shape": question_shape(qid, text or ""),
        "entities": entities,
        "date_constraints": dates,
        "date_axis": date_axis,
        "sql_terms": sql_terms,
        "rag_terms": rag_terms,
        "log_terms": log_terms,
        "routing_hints": {
            "requires_sql": requires_sql,
            "requires_rag": rag_terms["requires_rag"],
            "requires_logs": log_terms["requires_logs"],
            "requires_finance_compute": bool(
                re.search(r"\b(roi|reconciliation|net cost|cash outflow|calculate|ratio|growth|variance|gap|mismatch)\b", text or "", re.I)
            ),
            "requires_refusal_check": constraints["missing_data_instruction"] or "-REF-" in qid,
            "requires_prompt_injection_check": True,
            "requires_render_or_ocr": bool(re.search(r"\b(render|OCR|image|PDF)\b", text or "", re.I)),
        },
        "constraints": constraints,
        "warnings": entity_warnings + constraint_warnings,
        "unresolved_terms": unresolved,
    }


__all__ = [
    "normalize_question_rule_based",
    "extract_rule_dates",
    "extract_rule_entities",
    "extract_rule_sql_terms",
    "infer_date_axis",
]
