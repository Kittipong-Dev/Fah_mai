# -*- coding: utf-8 -*-
"""Load the question set and the reference answers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from fahmai.agents.config import GROUND_TRUTH_CSV, QUESTIONS_CSV


def load_questions() -> dict[str, str]:
    """{question_id: question_text} in questions.csv order."""
    qdf = pd.read_csv(QUESTIONS_CSV)
    return dict(zip(qdf["id"], qdf["question"]))


def _suite_from_id(qid: str) -> str:
    parts = str(qid).split("-")
    return parts[2] if len(parts) > 2 else ""


def _confidence_from_id(qid: str) -> str:
    if "-INJ-" in str(qid):
        return "defend"
    if "-REF-" in str(qid):
        return "refusal"
    return "exact"


def load_ground_truth(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """{question_id: {confidence, answer, ...}} from a ground-truth CSV.

    Supports the repo schema (`id,suite,confidence,answer,source`) and the Opus
    review schema (`id,question,answer,explain`).
    """
    gt_path = Path(path) if path else GROUND_TRUTH_CSV
    if not gt_path.exists():
        return {}
    gt = pd.read_csv(gt_path).fillna("")
    out: dict[str, dict[str, Any]] = {}
    for _, row in gt.iterrows():
        record = row.to_dict()
        qid = str(record.get("id", ""))
        if not qid:
            continue
        record.setdefault("suite", _suite_from_id(qid))
        if not str(record.get("suite", "")).strip():
            record["suite"] = _suite_from_id(qid)
        record.setdefault("confidence", _confidence_from_id(qid))
        if not str(record.get("confidence", "")).strip():
            record["confidence"] = _confidence_from_id(qid)
        if "source" not in record and "explain" in record:
            record["source"] = record.get("explain", "")
        out[qid] = record
    return out


# convenience module-level map (questions.csv always ships with the repo)
QMAP = load_questions()
