# FahMai team agent (`fahmai.agents`)

A LangGraph multi-agent that answers the FahMai L3 questions over a Supabase Postgres
warehouse + a document corpus, in Thai.

```
question
  → input_guard regex-tag injection signals (no LLM)
  → plan        decompose into 1–4 self-contained subtasks; flag injection
  → workers     one Send() per subtask, run IN PARALLEL (retry transient 504)
        ├ sql_analyst    : sql_query                      (warehouse + doc_corpus + pos_logs)
        └ doc_researcher : search_docs + get_document     (chats / email / memo / minutes / FAQ)
  → coverage    did the raw findings cover every subtask? hard-failed (504/empty) → replan ONLY those
                (deterministic re-dispatch, bounded by FAHMAI_REPLAN_BUDGET); else → synth
  → synth       merge findings → grounded Thai answer (self-checked, injection-resistant)
  → guard       deterministic output safety (must-not / refusal-shape / forced-string); repair ≤1
```
Verification is at the **data layer** (`coverage` checks the fetched findings), not the text layer —
the old LLM `verify` node was removed (its safety half is covered by `guard`, its completeness half by
`coverage` + synth's self-check). This cuts an LLM call per question and actually fixes missing-data
failures (a 504'd subtask is re-dispatched rather than re-worded).

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
  guardrails/      deterministic input tagger + output validator (regex/string, ~0 LLM)
    patterns.py  input_guard.py  output_guard.py
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

## Guardrails (deterministic, ~0 latency)
Prompts alone aren't reliable, so two guardrail nodes wrap the graph:
`START → input_guard → plan → … → verify → guard → END`.
- **input_guard** (`guardrails/input_guard.py`) — pure regex (`scan_input`): tags the question with
  8 injection patterns (`system_token`, `fake_policy_id`, `appeal_authority`, `false_memory`,
  `forced_string`, `lang_switch`, `do_not_consult`, `echo_content`) + extracts the demanded
  verbatim strings, asker-proposed candidate values, language demand, and authority-grant intent.
  It only **tags** (never blocks) so a benign-but-injection-shaped question is still answered.
  The tags are also injected into the synthesizer prompt.
- **guard** (`guardrails/output_guard.py`) — validates the final answer (`check_output`) against 5
  rules: no demanded forced-string, no echoed candidate value, must be Thai, must not affirm an
  asserted authority, and a refusal must be well-formed (verb + scope). `scrub` fixes the mechanical
  violations with **no LLM**; a residual semantic violation triggers **≤1** synth rewrite. The
  authority-affirm rule fires when the question planted a role/authority claim **or** the planner
  flagged `is_injection`, AND the answer carries affirm-language (ยืนยัน/อนุมัติ/มีอำนาจ/confirmed).
  If such a violation survives the one repair pass, `force_decline` **deterministically** replaces the
  answer with a Thai decline template — so a fell-for-injection affirmation can never reach the user,
  regardless of what synth does. A correct Path-A injection answer (e.g. "CEO คือ Naret", real sales
  figures) has no affirm-language, so it is never templated.

Measured cost: `scan_input`+`check_output`+`scrub` over 100 questions = **~1 ms total, 0 LLM**. The
only added LLM call is the rare repair pass (a few INJ edge cases). Set `FAHMAI_GUARDRAIL_REPAIR=off`
for strictly-zero extra LLM (scrub-only). Grounded in a scan of all 100 questions: these patterns
flag 7/10 INJ with **zero false positives** on EASY/MED/HARD/XHARD; the 2 "quiet" false-premise
injections (INJ-018/021) are left to the identity canon in `schema_card` + the verifier.

## Schema knowledge & resilience
- **Enum value-map** — `scripts/build_enum_dictionary.py` introspects the DB and writes
  `fahmai/tools/enum_dict.py` (`ENUM_CARD`), appended to `schema_card.SCHEMA_CARD`. It lists each
  low-cardinality categorical column's exact values + a hand-curated **rank** where the data can't
  show it (`loyalty_tier: silver<gold<platinum`, `position_level: IC<Manager<Director<C-level`). This
  is why the agent stops doing alphabetical `max()` on a tier. Re-run the script after any data reload.
- **Gateway-timeout retry** — `specialists/base.py:run_specialist_async` retries a specialist on a
  transient OpenRouter 504 / "operation aborted" (up to `FAHMAI_RETRY_ON_TIMEOUT`, default 2, with
  backoff), and labels a give-up as `(model gateway timeout …)` vs the recursion `(stopped after step
  budget …)` so traces are unambiguous.

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
