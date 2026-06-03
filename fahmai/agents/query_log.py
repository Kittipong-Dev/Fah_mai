# -*- coding: utf-8 -*-
"""Append-only query log for future materialized-view design."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fahmai.agents.config import QUERY_LOG_PATH


def append_query_log(event: dict[str, Any]) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    try:
        QUERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with QUERY_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Query logging must never affect answering.
        return
