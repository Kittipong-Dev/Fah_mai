# -*- coding: utf-8 -*-
"""Backward-compatible shim — the agent now lives in the `fahmai.agents` package.

    uv run python run_submission.py            # all remaining (resumable)
    uv run python run_submission.py --limit 5  # first N missing (smoke)

Equivalent to `python main.py submit [--limit N]`.
"""
from __future__ import annotations

import asyncio
import sys

from fahmai.agents.runner import run_submission

if __name__ == "__main__":
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    raise SystemExit(asyncio.run(run_submission(limit=limit)))
