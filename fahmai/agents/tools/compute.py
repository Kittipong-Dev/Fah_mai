# -*- coding: utf-8 -*-
"""finance_compute_tool - deterministic calculations over verified numeric inputs."""
from __future__ import annotations

import json

from langchain_core.tools import tool

from fahmai.tools.compute_tool import compute_batch


@tool
def finance_compute_tool(payload_json: str) -> str:
    """Compute finance metrics from explicit numeric inputs.

    Input JSON must contain {"calculations": [...]} where each item has an operation such as
    ratio, roi_multiple, roi_gain, percentage_share, yoy_growth, variance, gap, or mismatch_days.
    """
    try:
        result = compute_batch(payload_json)
    except Exception as exc:  # noqa: BLE001
        result = {"status": "error", "calculations": [], "summary": "", "warnings": [str(exc)]}
    return json.dumps(result, ensure_ascii=False, default=str)
