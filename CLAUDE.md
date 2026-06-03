# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                    # install / sync all dependencies (run first)

# CLI (three subcommands)
uv run python main.py answer "L3-Q-EASY-001"   # answer one question by id or raw text
uv run python main.py submit [--limit N]        # resumable batch -> submission.csv
uv run python main.py eval                      # re-run failed questions vs ground_truth.csv

# Or use the installed script after uv sync
uv run fahmai answer "L3-Q-EASY-001"

# Smoke-test a single low-level tool (no graph, no LLM)
uv run python -m fahmai.tools.sql_tool
uv run python -m fahmai.tools.doc_tool

# DB connection check
uv run python -m fahmai.db

# Inspect a piece in isolation
uv run python -c "
from fahmai.agents.tools import sql_query_tool, search_docs_tool
print(sql_query_tool.invoke({'sql': 'select count(*) from dim_vendor'}))
"
```

## Environment

Copy `env` → `.env` at the repo root. Required keys:
- `OPEN_ROUTER` — powers both the chat LLM and embeddings (bge-m3)
- `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_PASSWORD` — Supabase Postgres
- `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT` — optional tracing (project: `fahmai`)

Runtime knobs (env overrides, all optional):
- `FAHMAI_MODEL` (default `google/gemma-4-31b-it`)
- `FAHMAI_CONCURRENCY` (default `3`) — parallel questions in submit
- `FAHMAI_Q_TIMEOUT` (default `600`) — per-question timeout in seconds
- `FAHMAI_DOC_K` (default `3`) — search results after dedup
- `FAHMAI_REPLAN_BUDGET` (default `1`) — max coverage→plan re-dispatch rounds
- `FAHMAI_GUARDRAIL_REPAIR` (default `on`) — LLM repair pass for residual violations

## Architecture

### Graph pipeline (`fahmai/agents/graph.py`)

```
input_guard → plan → workers (parallel Send) → coverage → synth → guard
```

- **input_guard** — pure regex, no LLM; tags `flags{}` (forced strings, candidate values, authority claims, lang demands) onto the state
- **plan** — LLM decomposes into 1–4 subtasks routed to `sql` or `doc`; on replan path re-dispatches only failed subtasks without calling the LLM again
- **workers** — one `Send()` per subtask, run in parallel; results accumulate via `operator.add` reducer on `findings`
- **coverage** — data-layer gate; if any finding is a hard-fail string (timeout/error/empty), re-dispatches those subtasks up to `REPLAN_BUDGET` times; otherwise passes to synth
- **synth** — merges all findings into a grounded Thai answer; also computes arithmetic the planner left out; receives guardrail constraints from `flags`
- **guard** — deterministic string scrub (forced strings, candidate echoes, weak refusals); semantic violations (not_thai, authority_affirm) loop back to synth ≤1 time; if still failing, emits `DECLINE_TEMPLATE`

State fields: `question`, `is_injection`, `subtasks`, `findings`, `draft`, `final`, `failed_subtasks`, `replan_attempts`, `feedback`, `flags`, `guard_attempts`.

### Two-layer tool system

```
fahmai/tools/          low-level Python functions (sql_query, search_docs, get_document)
fahmai/agents/tools/   LangChain @tool wrappers around the above → given to specialists
```

Never import `fahmai/agents/tools/` from outside agents. The raw functions in `fahmai/tools/` are safe to call directly for scripts/debugging.

### Specialist pattern (`fahmai/agents/specialists/`)

Each specialist is a `create_react_agent` (LangGraph prebuilt) with its own system prompt and tool list. To add a third specialist:
1. Create `fahmai/agents/specialists/my_specialist.py` with `KIND`, `RECURSION`, `build()`
2. Register it in `fahmai/agents/specialists/__init__.py` → `SPECIALISTS` dict
3. The planner prompt must know the new `specialist` value name

### Guardrails (`fahmai/agents/guardrails/`)

- `patterns.py` — all regexes: `INJECTION_PATTERNS`, `REFUSAL_VERBS`, `SCOPE_MARKERS`, `extract_forced_strings`, `extract_candidate_values`
- `input_guard.py` — `scan_input(question) → InputFlags`
- `output_guard.py` — `check_output()` finds violations; `scrub()` fixes mechanical ones; `force_decline()` emits the hardcoded Thai decline for authority affirmations

### Schema tools (`fahmai/tools/`)

- `schema_card.py` — `SCHEMA_CARD`: human-written compact schema injected into SQL analyst prompt
- `mschema.py` — `MSCHEMA`: auto-generated schema with real example values per column (run `scripts/build_mschema.py` to regenerate)
- `enum_dict.py` — `ENUM_CARD`: auto-generated enum domains + rank orderings (run `scripts/build_enum_dictionary.py` to regenerate)

### Critical DB rules (easy to get wrong)

- `dim_date.fiscal_year` is **Buddhist Era** (2567 = CE 2024). Always use `fiscal_year_ce` or filter by `business_event_date` for calendar year.
- `fact_promo_redemption` has **phantom duplicate rows** (same `txn_id` under different `channel`). Always `COUNT(DISTINCT txn_id)` for real redemption counts.
- Policy / as-of queries: `WHERE effective_date <= D AND (end_date IS NULL OR end_date > D)`
- Only 6 vendors in `dim_vendor`; V-007/V-013/V-014 appear in `fact_vendor_payment` but may not be in `dim_vendor`.
- `pos_logs` v1→v2 cutover **2025-04-01**: `discount_amt` renamed to `discount_total_thb`; v2 adds `payment_terminal_id`, `loyalty_tier_at_purchase`.
- `ocr_warranty_form`: join key is `claim_id_db` (not `claim_id`). SKU accuracy ~90% due to OCR errors — prefer `fact_warranty_claim` for authoritative SKU/amount.

### Submit / eval flow

- `submit` is **resumable**: only fills blank rows in `submission.csv`. Treat `(timeout)` / `(error:...)` cells as done — blank them manually to retry.
- `eval` re-runs a failed set and compares to `data/ground_truth.csv` using the heuristic in `fahmai/utils/scoring.py` (not the official grader).
- `submission_groundtruth.csv` in the repo root is a reference comparison file.
