"""Embedding helpers.

embed_batch     — OpenRouter (bge-m3, 1024-d) used by Supabase doc_vec search.
rag_embed_batch — vLLM endpoint (Qwen3-Embedding-8B, 4096-d) used by rag_chunks search.
"""
from __future__ import annotations

import os
import time

import httpx

from fahmai.db import ROOT  # noqa: F401  (import triggers .env load)

EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3")
EMBED_DIM = 1024
_URL = "https://openrouter.ai/api/v1/embeddings"

RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "qwen3-embedding")
RAG_EMBED_BASE_URL = os.getenv("RAG_EMBED_BASE_URL", "http://swarm-manager.modelharbor.com:56980/v1")
RAG_EMBED_API_KEY = os.getenv("RAG_EMBED_API_KEY", "EMPTY")
RAG_EMBED_DIM = 4096


def _call_embed(url: str, key: str, model: str, texts: list[str],
                retries: int = 5) -> list[list[float]]:
    """Shared HTTP retry logic for any OpenAI-compatible /v1/embeddings endpoint."""
    payload = {"model": model, "input": texts}
    last = None
    for attempt in range(retries):
        try:
            r = httpx.post(url, headers={"Authorization": f"Bearer {key}"},
                           json=payload, timeout=180)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("data"):
                    data = sorted(j["data"], key=lambda d: d["index"])
                    return [d["embedding"] for d in data]
                last = f"200 no-data: {str(j)[:150]}"
                time.sleep(2 ** attempt)
                continue
            last = f"{r.status_code} {r.text[:150]}"
            if r.status_code in (408, 429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(last)
        except (httpx.HTTPError, ValueError) as e:
            last = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"embed failed after {retries}: {last}")


def embed_batch(texts: list[str], retries: int = 5,
                model: str | None = None) -> list[list[float]]:
    key = os.environ["OPEN_ROUTER"]
    return _call_embed(_URL, key, model or EMBED_MODEL, texts, retries)


def rag_embed_batch(texts: list[str], retries: int = 5) -> list[list[float]]:
    """Embed using the vLLM Qwen3-Embedding-8B endpoint (4096-d) for rag_chunks search."""
    url = RAG_EMBED_BASE_URL.rstrip("/") + "/embeddings"
    return _call_embed(url, RAG_EMBED_API_KEY, RAG_EMBED_MODEL, texts, retries)


