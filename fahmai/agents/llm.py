# -*- coding: utf-8 -*-
"""Model factory — one place that knows how to build the chat LLM (OpenRouter)."""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from fahmai.agents.config import MODEL, OPENROUTER_BASE_URL


def make_llm(temperature: float = 0.0, model: str | None = None) -> ChatOpenAI:
    """A ChatOpenAI pointed at OpenRouter. `max_retries` rides out transient 5xx (e.g. 504)."""
    return ChatOpenAI(
        model=model or MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ["OPEN_ROUTER"],
        temperature=temperature,
        max_retries=5,
        timeout=120,
    )
