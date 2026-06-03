# -*- coding: utf-8 -*-
"""Parsing helpers for low-level ``search_docs`` text results."""
from __future__ import annotations

import re
from typing import Any

_BLOCK_RE = re.compile(
    r"(?ms)^\[(?P<score>-?\d+(?:\.\d+)?)\]\s+"
    r"(?P<doc_id>[^\n(]+?)\s+\((?P<meta>.*?)\)\n\s*(?P<snippet>.*?)(?=\n\[-?\d|\Z)"
)


def parse_meta(meta: str) -> dict[str, str]:
    parts = [part.strip() for part in (meta or "").split(",")]
    parsed: dict[str, str] = {}
    if len(parts) > 0:
        parsed["channel"] = parts[0]
    if len(parts) > 1:
        parsed["doc_date"] = parts[1]
    if len(parts) > 2:
        topic = parts[2]
        parsed["topic"] = topic.split("=", 1)[1] if "=" in topic else topic
    return parsed


def parse_search_docs_result(raw: str, search_type: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not raw:
        return [], ["no result"]
    if raw.startswith("(no matching documents)"):
        return [], ["no result"]
    if raw.startswith("SEARCH ERROR:"):
        return [], [raw]
    chunks: list[dict[str, Any]] = []
    for match in _BLOCK_RE.finditer(raw.strip()):
        meta = parse_meta(match.group("meta"))
        snippet = " ".join(match.group("snippet").split())
        chunks.append(
            {
                "source": search_type,
                "doc_id": match.group("doc_id").strip(),
                "chunk_id": f"{search_type}:{match.group('doc_id').strip()}",
                "score": float(match.group("score")),
                "text": snippet,
                "metadata": meta,
                "raw": match.group(0),
            }
        )
    if chunks:
        return chunks, []
    return [], ["no parseable retrieval chunks"]


def dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        key = (str(chunk.get("doc_id")), str(chunk.get("text", ""))[:160].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(chunk)
    return out


__all__ = ["dedupe_chunks", "parse_meta", "parse_search_docs_result"]
