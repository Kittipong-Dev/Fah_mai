# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                          # install / sync all deps (run first)

# CLI
uv run python main.py answer "L3-Q-EASY-001"     # one question (id or raw text)
uv run python main.py submit [--limit N]          # resumable batch -> submission.csv
uv run python main.py eval                        # re-run failed set vs ground_truth.csv

# REST API (see docs/API.md)
uv run uvicorn fahmai.api:app --host 0.0.0.0 --port 8000

# Progress monitor during a submit run (run from repo root)
uv run python scripts/progress.py

# Score submission against the independently-derived key
uv run python scripts/score_vs_gt_claude.py

# Smoke-test low-level pieces (no graph)
uv run python -m fahmai.db                        # Supabase connection check
uv run python -m fahmai.tools.sql_tool            # SQL tool against real DB
uv run python -c "from fahmai.agents.tools import sql_query_tool; print(sql_query_tool.invoke({'sql':'select count(*) from dim_vendor'}))"
```

There is **no test suite / linter** configured — validate changes by syntax-checking
(`python -c "import ast; ast.parse(open('f.py').read())"`), compiling the graph
(`uv run python -c "from fahmai.agents.graph import build_team; build_team()"`), and running
`main.py answer` on representative questions.

## Environment

Copy `env` → `.env` at repo root (it's git-ignored). The system talks to **four** model backends —
get these right or nodes silently fail / fall back:

```env
# Supabase warehouse (dim_*, fact_*, v_* views)
SUPABASE_URL / SUPABASE_KEY / SUPABASE_PASSWORD
OPEN_ROUTER                       # OpenRouter key: bge-m3 embeddings + (default) tool-calling LLM

# Orchestration LLM — classify/plan/synth/guard/compute (plain text-gen)
FAHMAI_MODEL=google/gemma-4-31B-it
FAHMAI_LLM_BASE_URL=http://swarm-manager.modelharbor.com:44428/v1   # vLLM GPU switcher
FAHMAI_LLM_API_KEY=EMPTY

# Tool-calling LLM — sql/doc/rag specialists (ReAct, needs native tool calls)
FAHMAI_TOOL_BASE_URL=https://openrouter.ai/api/v1   # keep on OpenRouter unless vLLM has --enable-auto-tool-choice
FAHMAI_TOOL_API_KEY=                                # blank -> uses OPEN_ROUTER
FAHMAI_TOOL_MODEL=google/gemma-4-31b-it

# RAG vector DB (pgvector, Qwen3-Embedding-8B 4096-d) — separate from Supabase
RAG_DATABASE_URL=postgresql+psycopg://...           # the rag_chunks DB
RAG_EMBED_MODEL=Qwen/Qwen3-Embedding-8B
RAG_EMBED_BASE_URL=http://localhost:6056/v1         # often an SSH tunnel to LANTA
RAG_EMBED_API_KEY=EMPTY

# Thai small LLM (/agent/thaillm) + OCR (typhoon-ocr-preview) — same switcher
FAHMAI_THAI_MODEL=typhoon-ai/typhoon-s-thaillm-8b-instruct-research-preview
FAHMAI_OCR_MODEL=typhoon-ocr-preview
FAHMAI_OCR_MAX_SIDE=2000          # downscale cap; >2000px images make the vision encoder 500
```

Other knobs: `FAHMAI_CONCURRENCY` (3), `FAHMAI_Q_TIMEOUT` (600), `FAHMAI_DOC_K` (3),
`FAHMAI_REPLAN_BUDGET` (1), `FAHMAI_SQL_VERIFY` (on), `FAHMAI_COMPUTE` (on),
`FAHMAI_GUARDRAIL_REPAIR` (on). LangSmith: `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT=fahmai`.

**Operational gotcha:** the vLLM switcher ports are *ephemeral* — if calls get "connection
refused", the server restarted on a new port; update `FAHMAI_LLM_BASE_URL`. Models also cold-start
(~30–75s) on first call. The RAG embed endpoint frequently needs an SSH tunnel up; if it's down,
`rag_search` silently falls back to keyword-only search (won't crash, weaker on chat questions).

## Architecture

### Graph pipeline (`fahmai/agents/graph.py`)

```
input_guard → classify → plan → dispatch
                                  ├─ parallel   → [worker × N]      ┐
                                  └─ sequential → sequential_worker ┘→ coverage → sql_verify → compute → synth → guard
```

- **input_guard** — pure regex (no LLM); tags `flags{}` (forced strings, candidate values, authority claims, lang demand)
- **classify** — LLM labels `question_type` (EASY/MED/HARD/XHARD) + `exec_mode` (parallel|sequential)
- **plan** — LLM decomposes into 1–4 subtasks routed to `sql`/`doc`/`rag`; injects a mode hint; on replan re-dispatches only failed subtasks (no LLM)
- **worker / sequential_worker** — parallel `Send()` fan-out, OR (HARD/XHARD) one-at-a-time where each subtask sees prior findings as context
- **coverage** — data-layer gate; re-dispatches hard-failed subtasks (504/empty/`"need more steps"`) up to `REPLAN_BUDGET`
- **sql_verify** — (MED/HARD/XHARD, superlative/aggregate claims only) independently re-checks a SQL finding with a different query shape; overwrites the original on the same subtask id
- **compute** — (HARD/XHARD) PAL pattern: LLM emits `{expression, operands}`, `fahmai/utils/safe_eval.py` computes deterministically — removes LLM arithmetic errors
- **synth** — merges findings → grounded Thai answer; uses `[compute]` values verbatim
- **guard** — deterministic scrub (forced strings/candidate echoes/weak refusals); semantic violations (not_thai, authority_affirm) loop back to synth ≤1×, else `DECLINE_TEMPLATE`

The compiled graph is a lazily-built **cached singleton** (`get_team()`); importing the module makes no LLM calls.

### Two LLM factories (`fahmai/agents/llm.py`)

- `make_llm()` — orchestration nodes; honors a per-request `ContextVar` model override (used by `/agent/thaillm`)
- `make_tool_llm()` — specialist ReAct agents; uses `FAHMAI_TOOL_*` because they need native tool-calling

Only `make_tool_llm`'s endpoint must support tool calls. This split exists because the local vLLM
Gemma was launched without `--enable-auto-tool-choice`, so specialists stay on OpenRouter.

### Three specialists (`fahmai/agents/specialists/`)

Each is a `create_react_agent` with its own prompt + tools. To add one: create a module with
`KIND`/`RECURSION`/`build()`, register in `specialists/__init__.py` `SPECIALISTS`, and teach the
planner prompt the new `specialist` value.

- `sql_analyst` — Supabase warehouse via `sql_query_tool` (text-to-SQL)
- `doc_researcher` — Supabase `doc_corpus`/`doc_vec` (bge-m3 1024-d) via `search_docs`/`get_document`
- `rag_researcher` — pgvector `rag_chunks` (Qwen3 4096-d) via `rag_search_tool`

### Two vector stores

| Store | Table | Dims | Content |
|---|---|---|---|
| Supabase | `doc_vec` ⋈ `doc_corpus` | 1024 (bge-m3) | email, memo, minutes, kb, chats |
| pgvector (`fahmai/rag_db.py`) | `rag_chunks` | 4096 (Qwen3) | chat_line_oa/works, pos_log, web_log, l1_kb, ops/fin reports |

`fahmai/embed.py`: `embed_batch()` = bge-m3 via OpenRouter; `rag_embed_batch()` = Qwen3 via the vLLM endpoint.

### Two-layer tools

`fahmai/tools/` = low-level Python (sql_query, search_docs, get_document) — safe to call directly.
`fahmai/agents/tools/` = LangChain `@tool` wrappers handed to specialists — don't import from outside agents.

### Schema artifacts (`fahmai/tools/`)
- `schema_card.py` (`SCHEMA_CARD`) — hand-written compact schema injected into the SQL prompt
- `mschema.py` (`MSCHEMA`), `enum_dict.py` (`ENUM_CARD`) — auto-generated (regen via `scripts/build_mschema.py`, `scripts/build_enum_dictionary.py`)

### API (`fahmai/api.py`, `fahmai/ocr.py`) — see `docs/API.md`
- `POST /agent/local` — agent on local Gemma-31B → `{id, answer, total_output_token}`
- `POST /agent/thaillm` — same agent, orchestration overridden to the Thai LLM
- `POST /ocr` — `{id, header, transaction[]}` base64 image/PDF → `{id, answer:{header, transaction[], total_output_token}}`; auto-detects image vs PDF, rasterizes PDF pages, downscales >2000px before OCR
- `total_output_token` is summed via a `BaseCallbackHandler` (`_TokenCounter`) passed through the graph

## Critical DB rules (easy to get wrong)

- `dim_date.fiscal_year` is **Buddhist Era** (2567 = CE 2024). Use `fiscal_year_ce` or filter `business_event_date` by calendar year. For year filters in SQL, **never** key off `as_of_date` (a fixed 2026-01-15 release snapshot) — that wrongly makes a populated year look empty.
- `fact_promo_redemption` has **phantom duplicate rows** (same `txn_id`, different `channel`). Use `COUNT(DISTINCT txn_id)`.
- Policy / as-of queries: `WHERE effective_date <= D AND (end_date IS NULL OR end_date > D)`.
- Per-group rates (e.g. returns/sales per branch): compute numerator and denominator grouped by the **same** key over **all** groups; don't drop REMOTE/HQ.
- `dim_vendor` has only 6 rows; some vendor_ids in fact tables aren't there.
- `pos_logs` v1→v2 cutover **2025-04-01**: `discount_amt`→`discount_total_thb`; v2 adds `payment_terminal_id`, `loyalty_tier_at_purchase`.
- Document/thread **counts** are SQL aggregates over `doc_corpus` (has `channel`/`topic`/`doc_date`), NOT a RAG vector task.

## Data / eval files
- `data/questions.csv` (100 L3 questions), `data/ground_truth.csv` (official key)
- `submission.csv` — latest agent output; `submit` is resumable (fills only blank rows; `(timeout)`/`(error)` cells count as done — blank to retry)
- `gt_claude.csv` — independent answer key derived by direct DB queries (`scripts/build_gt_claude.py`), with an `explain` column; useful as a stricter reference than the heuristic scorer in `fahmai/utils/scoring.py`
- The agent README (`fahmai/agents/README.md`) documents the original notebook→package migration and debugging tips.
