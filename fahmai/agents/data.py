# -*- coding: utf-8 -*-
"""Load the question set and the reference answers."""
from __future__ import annotations

import pandas as pd

from fahmai.agents.config import GROUND_TRUTH_CSV, QUESTIONS_CSV


def load_questions() -> dict[str, str]:
    """{question_id: question_text} in questions.csv order."""
    qdf = pd.read_csv(QUESTIONS_CSV)
    return dict(zip(qdf["id"], qdf["question"]))


def load_ground_truth() -> dict[str, dict]:
    """{question_id: {confidence, answer, ...}} from data/ground_truth.csv (if present)."""
    if not GROUND_TRUTH_CSV.exists():
        return {}
    gt = pd.read_csv(GROUND_TRUTH_CSV).fillna("")
    return {r["id"]: r.to_dict() for _, r in gt.iterrows()}


# convenience module-level map (questions.csv always ships with the repo)
QMAP = load_questions()
