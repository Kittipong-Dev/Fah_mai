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

# --- model ---
MODEL = os.getenv("FAHMAI_MODEL", "google/gemma-4-31b-it")

# Orchestration nodes (classify / plan / synth / guard / compute) — plain text generation.
# If FAHMAI_LLM_BASE_URL is set, use that vLLM endpoint directly.
LLM_BASE_URL = os.getenv("FAHMAI_LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY_ENV = "FAHMAI_LLM_API_KEY" if os.getenv("FAHMAI_LLM_BASE_URL") else "OPEN_ROUTER"

# Specialist agents (sql_analyst / doc_researcher / rag_researcher / sql_verifier) need
# native tool-calling. Use FAHMAI_TOOL_BASE_URL if provided; otherwise same as LLM_BASE_URL.
# If the primary vLLM server lacks --enable-auto-tool-choice, point this at OpenRouter.
TOOL_BASE_URL = os.getenv("FAHMAI_TOOL_BASE_URL", LLM_BASE_URL)
# For tool key: use FAHMAI_TOOL_API_KEY if set and non-empty, else fall back to OPEN_ROUTER
_tool_key = os.getenv("FAHMAI_TOOL_API_KEY", "")
TOOL_API_KEY_ENV = "FAHMAI_TOOL_API_KEY" if _tool_key else "OPEN_ROUTER"
TOOL_MODEL = os.getenv("FAHMAI_TOOL_MODEL", MODEL)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"  # kept for embed.py

# OCR model (typhoon-ocr-preview) — served by the same GPU-switcher as the orchestration LLM.
OCR_MODEL = os.getenv("FAHMAI_OCR_MODEL", "typhoon-ocr-preview")
OCR_BASE_URL = os.getenv("FAHMAI_OCR_BASE_URL", LLM_BASE_URL)
OCR_API_KEY_ENV = "FAHMAI_OCR_API_KEY" if os.getenv("FAHMAI_OCR_API_KEY") else LLM_API_KEY_ENV

# Thai small LLM (served by the same switcher) — used by the /agent/thaillm endpoint.
THAI_MODEL = os.getenv("FAHMAI_THAI_MODEL", "typhoon-ai/typhoon-s-thaillm-8b-instruct-research-preview")

# --- runtime knobs (override via env) ---
CONCURRENCY = int(os.getenv("FAHMAI_CONCURRENCY", "3"))      # questions in flight
PER_Q_TIMEOUT = int(os.getenv("FAHMAI_Q_TIMEOUT", "600"))   # seconds per question
DOC_K = int(os.getenv("FAHMAI_DOC_K", "3"))                 # search results kept after dedup (was 8)
SQL_RECURSION = 18      # sql specialist step budget (multi-step queries)
DOC_RECURSION = 8       # doc specialist step budget (anti-loop)
TEAM_RECURSION = 60     # whole-graph recursion limit
REPLAN_BUDGET = int(os.getenv("FAHMAI_REPLAN_BUDGET", "1"))  # coverage->plan re-dispatch rounds

# guardrails: "on" = deterministic scrub + ≤1 LLM repair for residual semantic violations;
# "off" = scrub-only (strictly 0 extra LLM calls).
GUARDRAIL_REPAIR = os.getenv("FAHMAI_GUARDRAIL_REPAIR", "on").lower() not in ("0", "off", "false")

# retry a specialist this many extra times on a transient gateway timeout (504/aborted)
RETRY_ON_TIMEOUT = int(os.getenv("FAHMAI_RETRY_ON_TIMEOUT", "2"))

# sql self-verify: independently re-check superlative/aggregate SQL claims (MED/HARD/XHARD).
SQL_VERIFY = os.getenv("FAHMAI_SQL_VERIFY", "on").lower() not in ("0", "off", "false")
# compute node: deterministic Python arithmetic over findings (HARD/XHARD).
COMPUTE_NODE = os.getenv("FAHMAI_COMPUTE", "on").lower() not in ("0", "off", "false")

# --- data paths ---
DATA = ROOT / "data"
QUESTIONS_CSV = DATA / "questions.csv"
GROUND_TRUTH_CSV = DATA / "ground_truth.csv"
SUBMISSION_CSV = ROOT / "submission.csv"
