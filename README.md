# fahmai-hack

LangGraph multi-agent that answers the FahMai L3 questions over a Supabase Postgres warehouse
+ a document corpus (Thai/EN). Super AI Engineer S6 — FahMai finale.

## Setup
```bash
uv sync                                   # dev env (installs the `fahmai` package editable)
# minimal runtime instead:  pip install -r requirements.txt && pip install -e .
```
Create `.env` with: `OPEN_ROUTER`, `SUPABASE_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY`,
and (optional) `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT=fahmai`.

## Run
```bash
python main.py answer "L3-Q-EASY-001"     # one question (id or text)
python main.py submit                     # resumable batch → submission.csv
python main.py eval                       # regression compare vs data/ground_truth.csv
```

## Layout
```
fahmai/                 installable package
  agents/               the team agent  (see fahmai/agents/README.md)
  tools/                sql_tool, doc_tool, schema_card  (low-level)
  utils/                shared helpers: json_parse, dedup, scoring
  ingestion/            load tables/docs into Supabase; build embeddings
  db.py  embed.py       Postgres connection (session pooler) + OpenRouter embeddings
main.py                 CLI shim → fahmai.agents
data/                   questions.csv · ground_truth.csv (reference answers) · submission.csv
scripts/                one-off ingestion / validation / analysis helpers
notebooks/              01 preprocess · 02 original agent prototype (legacy)
```
The agent architecture, the routing/RAG/refusal fixes, and a debugging guide are documented in
**`fahmai/agents/README.md`**.

## Data ingestion (one-time, already loaded)
```bash
uv run python -m fahmai.ingestion.load_to_supabase   # CSV tables → Postgres
uv run python -m fahmai.ingestion.load_docs          # docs → doc_corpus
uv run python -m fahmai.ingestion.embed_docs         # embeddings → doc_vec
```
