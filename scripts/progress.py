# -*- coding: utf-8 -*-
"""Print submission.csv progress. Usage: uv run python scripts/progress.py"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "submission.csv").fillna("")
resp = df["response"].astype(str).str.strip()
done = resp.ne("").sum()
errors = df[resp.str.startswith("(")]["id"].tolist()
print(f"{done}/100 done | {100 - done} left | {len(errors)} errors", end="")
print(f"  errors={errors}" if errors else "")
