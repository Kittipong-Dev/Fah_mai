# -*- coding: utf-8 -*-
"""Tolerant JSON extraction for LLM outputs (planner / verifier)."""
from __future__ import annotations

import json
import re


def parse_json(s: str):
    """Parse JSON from an LLM response, falling back to the first {...} block if it's wrapped
    in prose / code fences. Returns the object, or None if nothing parses."""
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None
