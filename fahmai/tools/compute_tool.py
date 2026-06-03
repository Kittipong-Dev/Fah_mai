# -*- coding: utf-8 -*-
"""Deterministic finance/compute helpers for verified numeric evidence."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
from typing import Any


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError("missing numeric input")
    text = str(value).strip().replace(",", "")
    if not text:
        raise ValueError("missing numeric input")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric input: {value}") from exc


def _date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def _number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def compute_operation(spec: dict[str, Any]) -> dict[str, Any]:
    op = str(spec.get("operation") or "").strip().lower()
    label = str(spec.get("label") or op)
    if op in {"ratio", "roi_multiple"}:
        numerator = _dec(spec.get("numerator"))
        denominator = _dec(spec.get("denominator"))
        if denominator == 0:
            raise ValueError("division by zero")
        value = numerator / denominator
        formula = "numerator / denominator"
    elif op == "roi_gain":
        returns = _dec(spec.get("return_value"))
        investment = _dec(spec.get("investment"))
        if investment == 0:
            raise ValueError("division by zero")
        value = (returns - investment) / investment
        formula = "(return_value - investment) / investment"
    elif op in {"percentage_share", "share"}:
        part = _dec(spec.get("part"))
        total = _dec(spec.get("total"))
        if total == 0:
            raise ValueError("division by zero")
        value = part / total * Decimal(100)
        formula = "part / total * 100"
    elif op in {"yoy_growth", "growth"}:
        current = _dec(spec.get("current"))
        previous = _dec(spec.get("previous"))
        if previous == 0:
            raise ValueError("division by zero")
        value = (current - previous) / previous * Decimal(100)
        formula = "(current - previous) / previous * 100"
    elif op == "variance":
        actual = _dec(spec.get("actual"))
        expected = _dec(spec.get("expected"))
        value = actual - expected
        formula = "actual - expected"
    elif op == "gap":
        baseline = _dec(spec.get("baseline"))
        observed = _dec(spec.get("observed"))
        value = baseline - observed
        formula = "baseline - observed"
    elif op in {"mismatch_days", "days_between"}:
        start = _date(spec.get("start_date"))
        end = _date(spec.get("end_date"))
        value = Decimal((end - start).days)
        formula = "end_date - start_date"
    else:
        raise ValueError(f"unsupported operation: {op or '(blank)'}")
    return {
        "label": label,
        "operation": op,
        "formula": formula,
        "value": _number(value),
        "unit": spec.get("unit"),
        "inputs": {k: v for k, v in spec.items() if k not in {"label", "operation", "unit"}},
    }


def compute_batch(payload: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    calculations = payload.get("calculations") if isinstance(payload, dict) else None
    if not isinstance(calculations, list) or not calculations:
        return {
            "status": "missing_input",
            "calculations": [],
            "summary": "No calculations supplied.",
            "warnings": ["payload.calculations must be a non-empty list"],
        }
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, spec in enumerate(calculations, start=1):
        try:
            out.append(compute_operation(spec))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"calculation {idx}: {exc}")
    status = "success" if out and not warnings else ("partial" if out else "missing_input")
    return {
        "status": status,
        "calculations": out,
        "summary": f"Computed {len(out)} calculation(s)." if out else "No calculations computed.",
        "warnings": warnings,
    }
