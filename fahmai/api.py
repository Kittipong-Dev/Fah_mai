# -*- coding: utf-8 -*-
"""FahMai answer API.

POST /answer  {"question": "..."}
->            {"id": "<uuid>", "answer": "...", "total_output_token": N}

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

from fahmai.agents.graph import aanswer, get_team


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


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@app.post("/answer", response_model=AnswerResponse)
async def answer_question(req: QuestionRequest) -> AnswerResponse:
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be blank")

    counter = _TokenCounter()
    try:
        ans = await aanswer(req.question, callbacks=[counter])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AnswerResponse(
        id=str(uuid.uuid4()),
        answer=ans,
        total_output_token=counter.total_tokens,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
