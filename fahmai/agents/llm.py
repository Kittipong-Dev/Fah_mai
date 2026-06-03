# -*- coding: utf-8 -*-
"""Model factory — supports both OpenRouter and direct vLLM endpoints.

If FAHMAI_LLM_BASE_URL is set in .env, all LLM calls go to that vLLM server
(using FAHMAI_LLM_API_KEY, default "EMPTY"). Otherwise falls back to OpenRouter
using OPEN_ROUTER key.
"""
from __future__ import annotations

import contextvars
import os

from langchain_openai import ChatOpenAI

from fahmai.agents.config import (
    LLM_API_KEY_ENV, LLM_BASE_URL, MODEL,
    TOOL_API_KEY_ENV, TOOL_BASE_URL, TOOL_MODEL,
)

# Per-request override for the orchestration model (set by the API for /agent/thaillm).
# A ContextVar propagates correctly across the async graph (copied into each Send task).
_MODEL_OVERRIDE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fahmai_model_override", default=None
)


def set_model_override(model: str | None) -> contextvars.Token:
    """Override the orchestration model for the current async context. Returns a reset token."""
    return _MODEL_OVERRIDE.set(model)


def reset_model_override(token: contextvars.Token) -> None:
    _MODEL_OVERRIDE.reset(token)


def make_llm(temperature: float = 0.0, model: str | None = None) -> ChatOpenAI:
    """Orchestration LLM (classify / plan / synth / guard / compute) — plain text generation."""
    api_key = os.environ.get(LLM_API_KEY_ENV, "EMPTY")
    chosen = model or _MODEL_OVERRIDE.get() or MODEL
    return ChatOpenAI(
        model=chosen,
        base_url=LLM_BASE_URL,
        api_key=api_key,
        temperature=temperature,
        max_retries=5,
        timeout=120,
    )


def make_tool_llm(temperature: float = 0.0, model: str | None = None) -> ChatOpenAI:
    """Tool-calling LLM for specialists (sql / doc / rag / sql_verifier).

    Uses FAHMAI_TOOL_BASE_URL + FAHMAI_TOOL_MODEL if set, otherwise same endpoint as make_llm().
    Point FAHMAI_TOOL_BASE_URL at OpenRouter if the primary vLLM server lacks tool-call support.
    """
    api_key = os.environ.get(TOOL_API_KEY_ENV, "EMPTY")
    return ChatOpenAI(
        model=model or TOOL_MODEL,
        base_url=TOOL_BASE_URL,
        api_key=api_key,
        temperature=temperature,
        max_retries=5,
        timeout=120,
    )
