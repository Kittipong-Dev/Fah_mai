# -*- coding: utf-8 -*-
"""Execute the team-agent notebook's code cells (except the final loop), then run 2 questions
to validate the notebook works end-to-end before hand-off."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
nb = json.loads((ROOT / "notebooks" / "02_team_agent.ipynb").read_text(encoding="utf-8"))
code_cells = [c["source"] for c in nb["cells"] if c["cell_type"] == "code"]

ns: dict = {}
# run all but the last code cell (the 5-question loop)
for src in code_cells[:-1]:
    exec(src if isinstance(src, str) else "".join(src), ns)

import time
answer = ns["answer"]
QMAP = ns["QMAP"]
for qid in ["L3-Q-HARD-001", "L3-Q-XHARD-012"]:
    print("=" * 80)
    print(qid, "-", QMAP[qid][:80])
    t = time.perf_counter()
    a = answer(QMAP[qid])
    print(f"AGENT ({time.perf_counter()-t:.1f}s) ->", a)
