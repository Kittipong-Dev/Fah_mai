# -*- coding: utf-8 -*-
"""FahMai API.

POST /agent/local     {"question": "..."}  -> agent on the local Gemma-31B
POST /agent/thaillm   {"question": "..."}  -> agent on the Thai small LLM
    both return       {"id": "<uuid>", "answer": "...", "total_output_token": N}

POST /ocr             {"id","header","transaction":[...]}  (base64 image/pdf)
    returns           {"id", "answer": {"header","transaction":[...],"total_output_token"}}

total_output_token counts ALL tokens consumed across every LLM call in one request
(classify, plan, workers, sql_verify, compute, synth, guard) via a LangChain callback.

Run:
    uv run uvicorn fahmai.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from pydantic import BaseModel

import anyio

from fahmai.agents.config import THAI_MODEL
from fahmai.agents.graph import aanswer, get_team
from fahmai.agents.llm import reset_model_override, set_model_override
from fahmai.ocr import run_ocr


# ---------------------------------------------------------------------------
# Token-counting callback
# ---------------------------------------------------------------------------

class _TokenCounter(BaseCallbackHandler):
    """Accumulates token usage reported by every LLM call in the graph."""

    def __init__(self):
        super().__init__()
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        usage = (response.llm_output or {}).get("token_usage") or {}
        self.prompt_tokens     += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens      += usage.get("total_tokens", 0)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_team()          # warm up the graph + specialist agents at startup
    yield


app = FastAPI(
    title="FahMai Answer API",
    description="LangGraph multi-agent QA over the FahMai Supabase warehouse + RAG corpus.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    id: str
    answer: str
    total_output_token: int


class OCRRequest(BaseModel):
    id: str                       # question id (echoed back)
    header: str                   # base64-encoded header image/pdf (data-URL prefix optional)
    transaction: list[str] = []   # base64-encoded transaction images/pdfs


class OCRResponse(BaseModel):
    id: str
    answer: dict                  # {"header": "...", "transaction": ["...", ...], "total_output_token": N}


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

async def _run_agent(question: str, model: str | None) -> AnswerResponse:
    """Run the agent; `model` (if given) overrides the orchestration LLM for this request."""
    if not question.strip():
        raise HTTPException(status_code=422, detail="question must not be blank")

    counter = _TokenCounter()
    token = set_model_override(model) if model else None
    try:
        ans = await aanswer(question, callbacks=[counter])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if token is not None:
            reset_model_override(token)

    return AnswerResponse(
        id=str(uuid.uuid4()),
        answer=ans,
        total_output_token=counter.total_tokens,
    )


@app.post("/agent/local", response_model=AnswerResponse)
async def agent_local(req: QuestionRequest) -> AnswerResponse:
    """Agent powered by the local Gemma-31B (default orchestration model)."""
    return await _run_agent(req.question, model=None)


@app.post("/agent/thaillm", response_model=AnswerResponse)
async def agent_thaillm(req: QuestionRequest) -> AnswerResponse:
    """Agent with orchestration nodes running on the Thai small LLM."""
    return await _run_agent(req.question, model=THAI_MODEL)


def _strip_data_url(b64: str) -> str:
    """Remove an optional data-URL prefix:  data:image/png;base64,XXXX -> XXXX"""
    if b64.startswith("data:") and "," in b64:
        return b64.split(",", 1)[1]
    return b64


@app.post("/ocr", response_model=OCRResponse)
async def ocr(req: OCRRequest) -> OCRResponse:
    if not req.header.strip():
        raise HTTPException(status_code=422, detail="header must not be blank")

    total_tokens = 0

    def _ocr_one(b64: str) -> str:
        nonlocal total_tokens
        out = run_ocr(_strip_data_url(b64))
        total_tokens += out["total_output_token"]
        return out["result"]

    try:
        # run sequentially in a worker thread (sync httpx) to avoid blocking the loop
        def _process() -> dict:
            header_text = _ocr_one(req.header)
            txn_texts = [_ocr_one(b) for b in req.transaction if b and b.strip()]
            return {
                "header": header_text,
                "transaction": txn_texts,
                "total_output_token": total_tokens,
            }

        answer = await anyio.to_thread.run_sync(_process)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return OCRResponse(id=req.id, answer=answer)


@app.get("/health")
async def health():
    return {"status": "ok"}
