"""OpenRouter embeddings (bge-m3, 1024-d). Multilingual, strong Thai."""
from __future__ import annotations

import os
import time

import httpx

from fahmai.db import ROOT  # noqa: F401  (import triggers .env load)

EMBED_MODEL = os.getenv("EMBED_MODEL", "baai/bge-m3")
EMBED_DIM = 1024
_URL = "https://openrouter.ai/api/v1/embeddings"


def embed_batch(texts: list[str], retries: int = 5) -> list[list[float]]:
    key = os.environ["OPEN_ROUTER"]
    payload = {"model": EMBED_MODEL, "input": texts}
    last = None
    for attempt in range(retries):
        try:
            r = httpx.post(_URL, headers={"Authorization": f"Bearer {key}"},
                           json=payload, timeout=180)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("data"):
                    data = sorted(j["data"], key=lambda d: d["index"])
                    return [d["embedding"] for d in data]
                # 200 but no data (transient error body / rate notice) -> retry
                last = f"200 no-data: {str(j)[:150]}"
                time.sleep(2 ** attempt)
                continue
            last = f"{r.status_code} {r.text[:150]}"
            if r.status_code in (408, 429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(last)
        except (httpx.HTTPError, ValueError) as e:  # ValueError = bad JSON
            last = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"embed failed after {retries}: {last}")
