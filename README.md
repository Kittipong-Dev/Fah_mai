# FahMai Answer Agent

LangGraph multi-agent system that answers FahMai L3 questions over a Supabase Postgres warehouse,
a pgvector RAG corpus, and document stores (Thai/EN). Super AI Engineer S6 — FahMai finale.

---

## Pipeline

```
input_guard → classify → plan → dispatch
                                  ├── parallel   → [sql] [doc] [rag] workers → coverage
                                  └── sequential → sequential_worker          → coverage
                                                       ↓
                                               sql_verify → compute → synth → guard → answer
```

| Node | Role |
|---|---|
| `input_guard` | Regex-tag injection signals (no LLM) |
| `classify` | Label EASY/MED/HARD/XHARD + parallel/sequential mode |
| `plan` | Decompose into subtasks routed to `sql`, `doc`, or `rag` |
| `workers` | Parallel SQL analyst / doc researcher / RAG researcher |
| `sequential_worker` | HARD/XHARD: subtasks in order, each sees prior findings |
| `coverage` | Re-dispatch hard-failed subtasks (504/empty) up to 1 time |
| `sql_verify` | Independently re-check superlative/aggregate SQL claims |
| `compute` | Deterministic Python arithmetic over findings (PAL pattern) |
| `synth` | Merge findings → grounded Thai answer |
| `guard` | Scrub forced strings / echoed values / authority affirmations |

---

## Setup

```bash
uv sync                    # install all deps (fastapi, uvicorn, langgraph, etc.)
cp env .env                # or create .env with the keys below
```

### Required `.env` keys

```env
# Supabase warehouse
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_KEY=<anon-or-service-key>
SUPABASE_PASSWORD=<db-password>

# Embeddings — OpenRouter (bge-m3 1024-d for doc_vec)
OPEN_ROUTER=sk-or-...

# RAG vector search — Qwen3-Embedding-8B 4096-d (SSH tunnel or direct)
RAG_DATABASE_URL=postgresql+psycopg://fahmai_app:<pwd>@<host>:<port>/fahmai
RAG_EMBED_MODEL=Qwen/Qwen3-Embedding-8B
RAG_EMBED_BASE_URL=http://localhost:6056/v1
RAG_EMBED_API_KEY=EMPTY

# LLM for orchestration nodes (classify / plan / synth / guard)
FAHMAI_MODEL=google/gemma-4-31B-it
FAHMAI_LLM_BASE_URL=http://swarm-manager.modelharbor.com:57851/v1
FAHMAI_LLM_API_KEY=EMPTY

# LLM for specialist agents (sql / doc / rag) — needs tool-calling support
# Leave FAHMAI_TOOL_BASE_URL unset to use OpenRouter, or point at a vLLM server
# that has --enable-auto-tool-choice --tool-call-parser gemma3
FAHMAI_TOOL_BASE_URL=https://openrouter.ai/api/v1
FAHMAI_TOOL_API_KEY=            # blank = use OPEN_ROUTER key
FAHMAI_TOOL_MODEL=google/gemma-4-31b-it

# Optional: LangSmith tracing
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=fahmai
```

---

## Run (CLI)

```bash
uv run python main.py answer "L3-Q-EASY-001"   # one question (id or text)
uv run python main.py submit [--limit N]        # resumable batch → submission.csv
uv run python main.py eval                      # regression compare vs data/ground_truth.csv
```

## Run (REST API)

```bash
uv run uvicorn fahmai.api:app --host 0.0.0.0 --port 8000
```

**POST** `/answer`
```json
{ "question": "FahMai มีสาขาทั้งหมดกี่แห่ง" }
```
**Response**
```json
{
  "id": "uuid",
  "answer": "FahMai มีสาขาทั้งหมด 11 แห่ง",
  "total_output_token": 12345
}
```

Interactive docs: **http://localhost:8000/docs** · Full API reference: **[docs/API.md](docs/API.md)**

The API exposes two endpoints:
- `POST /answer` — ask the agent a question → `{id, answer, total_output_token}`
- `POST /ocr` — OCR a header + transaction documents (image/PDF base64) → `{id, answer:{header, transaction[], total_output_token}}`

Progress monitor (during batch):
```bash
uv run python scripts/progress.py
```

---

## Layout

```
fahmai/
  agents/
    graph.py          full pipeline (classify → sql_verify → compute → synth → guard)
    config.py         env + knobs (MODEL, LLM_BASE_URL, TOOL_BASE_URL, CONCURRENCY…)
    llm.py            make_llm() orchestration  /  make_tool_llm() specialists
    prompts/          one file per role: classify · planner · sql · doc · rag · synth · compute · sql_verify
    specialists/      sql_analyst · doc_researcher · rag_researcher
    tools/            LangChain @tool wrappers (sql_query · search_docs · get_document · rag_search)
    guardrails/       input_guard (regex) + output_guard (scrub + repair)
  tools/              low-level DB functions (sql_tool · doc_tool · schema_card · mschema · enum_dict)
  utils/              json_parse · dedup · scoring · safe_eval · trace_log
  db.py               Supabase engine (session pooler)
  rag_db.py           pgvector RAG engine
  embed.py            embed_batch() bge-m3 1024-d  /  rag_embed_batch() Qwen3 4096-d
  api.py              FastAPI REST endpoint
main.py               CLI shim → fahmai.agents.runner
data/
  questions.csv       100 L3 questions (EASY/MED/HARD/XHARD/REF/INJ)
  ground_truth.csv    official answer key
  submission.csv      latest agent answers
gt_claude.csv         independent answer key derived by direct DB queries + explain column
scripts/
  build_gt_claude.py  regenerate gt_claude.csv
  progress.py         live progress monitor for submit runs
  score_vs_gt_claude.py  score submission vs gt_claude key
```

---

## Knobs (env overrides)

| Variable | Default | Description |
|---|---|---|
| `FAHMAI_MODEL` | `google/gemma-4-31b-it` | Orchestration LLM model |
| `FAHMAI_LLM_BASE_URL` | OpenRouter | vLLM endpoint for orchestration |
| `FAHMAI_TOOL_MODEL` | same as MODEL | Specialist LLM model |
| `FAHMAI_TOOL_BASE_URL` | same as LLM_BASE_URL | vLLM endpoint for specialists |
| `FAHMAI_CONCURRENCY` | `3` | Parallel questions in submit |
| `FAHMAI_Q_TIMEOUT` | `600` | Per-question timeout (seconds) |
| `FAHMAI_SQL_VERIFY` | `on` | Enable sql_verify node |
| `FAHMAI_COMPUTE` | `on` | Enable compute (PAL) node |
| `FAHMAI_REPLAN_BUDGET` | `1` | Max coverage→plan re-dispatch rounds |
| `FAHMAI_GUARDRAIL_REPAIR` | `on` | LLM repair pass for output violations |
