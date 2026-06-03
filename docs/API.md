# FahMai API

FastAPI service exposing the FahMai agent on two LLM backends and document OCR.

| Endpoint | Purpose | Backend model |
|---|---|---|
| `POST /agent/local` | Full agent | local Gemma-4-31B (default) |
| `POST /agent/thaillm` | Full agent | Thai small LLM (typhoon-s-thaillm-8b) |
| `POST /ocr` | Document OCR | typhoon-ocr-preview |

## Run

```bash
uv run uvicorn fahmai.api:app --host 0.0.0.0 --port 8000
```

Interactive Swagger docs: **http://localhost:8000/docs**

Health check:
```bash
curl http://localhost:8000/health        # -> {"status":"ok"}
```

---

## 1. `POST /agent/local` and `POST /agent/thaillm` — ask the agent

Both run the full LangGraph pipeline (classify → plan → workers → sql_verify → compute → synth →
guard) and return a grounded Thai answer plus total token usage across every LLM call in the request.
They differ only in which model powers the **orchestration nodes**:

- **`/agent/local`** — local Gemma-4-31B (`FAHMAI_MODEL`)
- **`/agent/thaillm`** — Thai small LLM (`FAHMAI_THAI_MODEL`, default `typhoon-s-thaillm-8b`)

> The tool-calling specialists (sql / doc / rag) always use `FAHMAI_TOOL_*` regardless of endpoint —
> only the orchestration model changes.

### Request (same for both)
```json
{ "question": "FahMai มีสาขาทั้งหมดกี่แห่ง" }
```
| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | yes | The question (Thai or English) |

### Response (same for both)
```json
{
  "id": "b1f0c3e2-...-uuid",
  "answer": "FahMai มีสาขาทั้งหมด 11 แห่ง",
  "total_output_token": 12345
}
```
| Field | Type | Description |
|---|---|---|
| `id` | string | Random UUID for the request |
| `answer` | string | Final grounded answer (Thai) |
| `total_output_token` | int | Sum of tokens (prompt+completion) across all LLM calls in this request |

### Example
```bash
# local Gemma-31B
curl -s -X POST http://localhost:8000/agent/local \
  -H "Content-Type: application/json" \
  -d '{"question": "FahMai มีสาขาทั้งหมดกี่แห่ง"}'

# Thai small LLM
curl -s -X POST http://localhost:8000/agent/thaillm \
  -H "Content-Type: application/json" \
  -d '{"question": "FahMai มีสาขาทั้งหมดกี่แห่ง"}'
```

### Errors
| Code | Meaning |
|---|---|
| 422 | `question` blank |
| 500 | Agent / upstream LLM failure (detail in body) |

---

## 2. `POST /ocr` — OCR a header + transaction documents

OCRs a bank-statement-style bundle: one `header` document plus N `transaction` documents.
Each document may be an **image** (PNG/JPEG/WEBP/GIF) or a **PDF** (rasterized per page).
Uses the `typhoon-ocr-preview` model on the GPU switcher.

### Request
```json
{
  "id": "BS-KBANK-OPER-2567-01",
  "header": "<BASE64>",
  "transaction": ["<BASE64>", "<BASE64>", "..."]
}
```
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Caller's id — echoed back unchanged |
| `header` | string | yes | Base64 of the header image/PDF. `data:...;base64,` prefix optional (auto-stripped) |
| `transaction` | string[] | no | Base64 of each transaction image/PDF (default `[]`) |

### Response
```json
{
  "id": "BS-KBANK-OPER-2567-01",
  "answer": {
    "header": "<extracted text of header>",
    "transaction": ["<text of txn 1>", "<text of txn 2>", "..."],
    "total_output_token": 27866
  }
}
```
| Field | Type | Description |
|---|---|---|
| `id` | string | Echoed from the request |
| `answer.header` | string | OCR text of the header document |
| `answer.transaction` | string[] | OCR text per transaction document, in order |
| `answer.total_output_token` | int | Total tokens across all OCR calls |

### Behavior notes
- **Image vs PDF** auto-detected by magic bytes; PDFs are rasterized page-by-page (200 DPI) and
  pages are concatenated with `--- page N ---` markers within that document's text.
- **Auto-downscale**: any image/PDF page whose longest side exceeds **2000 px** is downscaled
  before OCR (the vision encoder returns HTTP 500 on larger images). Override with
  `FAHMAI_OCR_MAX_SIDE`.
- The model returns text as markdown (tables for tabular statements), Thai + English supported.
- `transaction` items that are blank are skipped.

### Example
```bash
python3 - <<'PY'
import base64, json, urllib.request
d = "/path/to/picture"
b64 = lambda f: base64.b64encode(open(f"{d}/{f}","rb").read()).decode()
req = {
  "id": "BS-KBANK-OPER-2567-01",
  "header": b64("BS-KBANK-OPER-2567-01_header.png"),
  "transaction": [
    b64("BS-KBANK-OPER-2567-01_transactions_p1.png"),
    b64("BS-KBANK-OPER-2567-01_transactions_p2.png"),
    b64("BS-KBANK-OPER-2567-01_transactions_p3.png"),
  ],
}
r = urllib.request.urlopen(urllib.request.Request(
    "http://localhost:8000/ocr",
    data=json.dumps(req).encode(),
    headers={"Content-Type": "application/json"}), timeout=600)
print(json.dumps(json.load(r), ensure_ascii=False, indent=2))
PY
```

### Errors
| Code | Meaning |
|---|---|
| 422 | `header` blank or invalid base64 |
| 500 | OCR model / upstream failure (detail in body) |

---

## Backend endpoints (vLLM GPU switcher)

Both `/answer` and `/ocr` call a vLLM "GPU switcher" that serves multiple models on one port
and hot-swaps the GPU between them. Configured in `.env`:

```env
# Orchestration LLM (classify / plan / synth / guard / compute)
FAHMAI_MODEL=google/gemma-4-31B-it
FAHMAI_LLM_BASE_URL=http://swarm-manager.modelharbor.com:44428/v1
FAHMAI_LLM_API_KEY=EMPTY

# Tool-calling specialists (sql / doc / rag) — needs --enable-auto-tool-choice;
# keep on OpenRouter unless the vLLM server supports tool calls
FAHMAI_TOOL_BASE_URL=https://openrouter.ai/api/v1
FAHMAI_TOOL_API_KEY=            # blank -> uses OPEN_ROUTER
FAHMAI_TOOL_MODEL=google/gemma-4-31b-it

# Thai small LLM for /agent/thaillm (same switcher)
FAHMAI_THAI_MODEL=typhoon-ai/typhoon-s-thaillm-8b-instruct-research-preview

# OCR model (same switcher by default)
FAHMAI_OCR_MODEL=typhoon-ocr-preview
FAHMAI_OCR_BASE_URL=            # blank -> uses FAHMAI_LLM_BASE_URL
FAHMAI_OCR_MAX_SIDE=2000        # downscale cap (longest side, px)
```

### GPU switcher direct API (for debugging)
The switcher itself is OpenAI-compatible:

```bash
# health (shows per-model queue depth + cumulative token usage)
curl http://swarm-manager.modelharbor.com:44428/health

# list models
curl http://swarm-manager.modelharbor.com:44428/v1/models
#  -> typhoon-ocr-preview
#     google/gemma-4-31B-it
#     typhoon-ai/typhoon-s-thaillm-8b-instruct-research-preview

# chat completion (LLM)
curl -s http://swarm-manager.modelharbor.com:44428/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemma-4-31B-it",
       "messages":[{"role":"user","content":"2+2?"}],
       "max_tokens":32}'

# OCR (multimodal): same endpoint, image as a data URL
curl -s http://swarm-manager.modelharbor.com:44428/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"typhoon-ocr-preview",
       "messages":[{"role":"user","content":[
         {"type":"image_url","image_url":{"url":"data:image/png;base64,<B64>"}},
         {"type":"text","text":"Extract all text."}]}],
       "max_tokens":4096}'
```

**Notes on the switcher**
- Models **wake from sleep / switch GPU** on first call — expect ~30–75 s cold-start.
- The vision encoder **rejects images larger than ~2000 px** on the longest side with HTTP 500;
  `/ocr` downscales automatically, but direct callers must resize first.
- Ports are **ephemeral** — if a port stops responding (connection refused), the switcher was
  restarted on a new port; update `FAHMAI_LLM_BASE_URL` / `FAHMAI_OCR_BASE_URL`.
