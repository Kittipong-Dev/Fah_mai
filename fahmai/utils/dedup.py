# -*- coding: utf-8 -*-
"""De-duplicate near-identical search-result blocks (FIX #3).

The doc corpus contains many synthetic near-duplicate chat variants (e.g. 30 paraphrases
of one DQ3-2025-04-05 exchange). `fahmai.tools.doc_tool.search_docs` returns its results as
blocks joined by newlines, each block being:

    [0.750] doc_id (channel, YYYY-MM-DD, topic=T)
        snippet text...

`dedup_blocks` keeps only the first block for each distinct snippet (compared on a
whitespace-normalized prefix) so the agent sees signal instead of 8 copies of boilerplate.
This is a string-level post-filter — `doc_tool.py` itself stays untouched.
"""
from __future__ import annotations

import re

_BLOCK_RE = re.compile(r"(?m)^\[\d")   # a block starts with a line like "[0.750] ..."


def _norm(text: str, n: int = 80) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()[:n]


def dedup_blocks(result: str, keep: int = 3) -> str:
    """Return at most `keep` blocks from a search_docs result, dropping near-duplicates."""
    if not result or result.startswith(("(no ", "SEARCH ERROR")):
        return result
    # split into blocks; each block = "[sim] header\n    snippet"
    parts = re.split(r"\n(?=\[\d)", result.strip())
    seen: set[str] = set()
    out: list[str] = []
    for block in parts:
        lines = block.split("\n", 1)
        snippet = lines[1] if len(lines) > 1 else lines[0]
        key = _norm(snippet)
        if key in seen:
            continue
        seen.add(key)
        out.append(block)
        if len(out) >= keep:
            break
    return "\n".join(out)
