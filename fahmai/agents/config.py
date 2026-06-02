# -*- coding: utf-8 -*-
"""Runtime configuration: load .env, enable LangSmith tracing, expose agent constants.

Importing this module has the side effect of loading `.env` and turning on LangSmith
tracing (if a key is present). `fahmai/agents/__init__.py` imports it first.
Supabase connection defaults live in `fahmai/db.py` (the session pooler), so nothing
DB-related needs to be set here.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]   # fahmai/agents/config.py -> repo root
load_dotenv(ROOT / ".env")

# --- LangSmith tracing (mirrors scripts/_trace_test.py) ---
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    _proj = (os.getenv("LANGSMITH_PROJECT") or "fahmai").strip().strip('"')
    os.environ["LANGSMITH_PROJECT"] = os.environ["LANGCHAIN_PROJECT"] = _proj

# --- model (OpenRouter) ---
MODEL = os.getenv("FAHMAI_MODEL", "google/gemma-4-31b-it")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# --- runtime knobs (override via env) ---
CONCURRENCY = int(os.getenv("FAHMAI_CONCURRENCY", "3"))      # questions in flight
PER_Q_TIMEOUT = int(os.getenv("FAHMAI_Q_TIMEOUT", "600"))   # seconds per question
DOC_K = int(os.getenv("FAHMAI_DOC_K", "3"))                 # search results kept after dedup (was 8)
SQL_RECURSION = 18      # sql specialist step budget (multi-step queries)
DOC_RECURSION = 8       # doc specialist step budget (anti-loop)
TEAM_RECURSION = 60     # whole-graph recursion limit
MAX_VERIFY_ATTEMPTS = 2 # synth<->verify retries

# --- data paths ---
DATA = ROOT / "data"
QUESTIONS_CSV = DATA / "questions.csv"
GROUND_TRUTH_CSV = DATA / "ground_truth.csv"
SUBMISSION_CSV = ROOT / "submission.csv"
