# FahMai team agent (`fahmai.agents`)

A LangGraph multi-agent that answers the FahMai L3 questions over a Supabase Postgres
warehouse + a document corpus, in Thai.

```
question
  → plan        decompose into 1–4 self-contained subtasks; flag injection
  → workers     one Send() per subtask, run IN PARALLEL
        ├ sql_analyst    : sql_query                      (warehouse + doc_corpus + pos_logs)
        └ doc_researcher : search_docs + get_document     (chats / email / memo / minutes / FAQ)
  → synth       merge findings → grounded Thai answer (injection-resistant)
  → verify      every part present & grounded? → retry ≤2, else finish
```

Model: **google/gemma-4-31b-it** via OpenRouter · LangSmith tracing (project `fahmai`).

## Quick start
```bash
uv sync                                   # installs the `fahmai` package editable
# or:  pip install -r requirements.txt && pip install -e .

python main.py answer "L3-Q-EASY-001"     # one question (id or raw text)
python main.py submit                     # resumable batch → submission.csv
python main.py submit --limit 5           # smoke: first 5 blank ids
python main.py eval                       # regression compare vs data/ground_truth.csv
```
`.env` must provide `OPEN_ROUTER`, `SUPABASE_PASSWORD`, `SUPABASE_URL`, and (optional)
`LANGSMITH_API_KEY`. DB connection defaults to the Supabase session pooler (see `fahmai/db.py`).

## Layout (one responsibility per file)
```
fahmai/agents/
  config.py        env load + LangSmith on + constants (MODEL, CONCURRENCY, DOC_K, recursion…)
  llm.py           make_llm() — the only place that builds the chat model
  prompts/         one system prompt per role
    planner.py  sql.py  doc.py  synth.py  verify.py
  tools/           LangChain @tool wrappers over fahmai.tools.*
    sql_query.py  search_docs.py  get_document.py
  specialists/     one sub-agent per module (drop a file here to add a 3rd specialist)
    base.py  sql_analyst.py  doc_researcher.py
  graph.py         State + nodes + build_team() + aanswer()/answer()
  data.py          load_questions()→QMAP, load_ground_truth()
  runner.py        resumable batch + the argparse CLI (cli())
  evaluate.py      re-run the previously-failed set, compare to ground_truth
```
Shared helpers live one level up in **`fahmai/utils/`** (not under `agents/`): `json_parse.py`
(planner/verify), `dedup.py` (search), `scoring.py` (eval triage). Lower-level pieces are reused,
not duplicated: `fahmai/tools/{sql_tool,doc_tool,schema_card}.py`, `fahmai/db.py`, `fahmai/embed.py`.

## What changed vs the original notebook (the 0.63 → fixes)
The agent used to live in `notebooks/02_team_agent.ipynb`. Three issues cost points; each fix is
localized so it's easy to see and revert:

1. **Routing** (`prompts/planner.py`) — values / ids / amounts / **schema** / **policy & as-of**
   values live in tables → always route to `sql`. Stops policy/invoice questions going to the
   doc/RAG worker (which can't answer them → false "ไม่พบข้อมูล").
2. **Defer-to-SQL** (`prompts/doc.py`) — the doc worker now replies "out of scope, SQL handles it"
   and STOPs for any value/id/number/schema ask, and caps searches (the corpus has many synthetic
   near-duplicate chats).
3. **Retrieval dedup** (`tools/search_docs.py` + `utils/dedup.py`) — over-fetch then collapse
   near-identical snippets, return `DOC_K` (=3) distinct docs instead of 8 boilerplate copies.
   `fahmai/tools/doc_tool.py` is untouched.

Plus grader-aligned **refusal / injection** rules in `prompts/synth.py`: a refusal carries
verb + topic + scope and never echoes a candidate value/fabricated count; never confirm an
authority/role asserted inside the question — verify it, else decline.

## Debugging
- **Per-question trace**: LangSmith project `fahmai` — every `aanswer` is one root run; inputs
  carry the question text. The worker tool calls (sql/doc) show exactly what was queried.
- **Run one question locally**: `python main.py answer "<id>"`.
- **Inspect a piece in isolation** (no graph):
  ```python
  from fahmai.agents.tools import sql_query_tool, search_docs_tool
  sql_query_tool.invoke({"sql": "select count(*) from dim_vendor"})
  search_docs_tool.invoke({"query": "CEO transition", "topic": "CEO"})
  from fahmai.agents.prompts import PLANNER_SYS   # read the exact prompt text
  ```
- **Knobs** via env: `FAHMAI_MODEL`, `FAHMAI_CONCURRENCY`, `FAHMAI_Q_TIMEOUT`, `FAHMAI_DOC_K`.

## Resume / retry note
`submit` treats any non-blank cell as done — `(timeout)`/`(error: …)` rows are NOT auto-retried.
To retry them, blank those cells in `submission.csv` and run `submit` again.
