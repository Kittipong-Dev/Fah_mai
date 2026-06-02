# -*- coding: utf-8 -*-
"""Regression harness: re-run the previously-failed questions and compare to ground_truth.

  python main.py eval        # (or: python -m fahmai.agents.evaluate)

Runs the agent on FAILED_SET (concurrency from config), prints id | confidence | PASS? |
ground_truth | agent, and writes data/eval_failed.csv. PASS is the heuristic in utils.scoring —
an aid, not the official grader.
"""
from __future__ import annotations

import asyncio
import csv

from fahmai.agents.config import CONCURRENCY, DATA
from fahmai.agents.data import QMAP, load_ground_truth
from fahmai.agents.graph import aanswer
from fahmai.utils import scoring

# the questions that were wrong/weak in the 0.63 run (routing, hallucination, injection, refusal)
FAILED_SET = [
    "L3-Q-EASY-011", "L3-Q-EASY-016", "L3-Q-EASY-022", "L3-Q-MED-010", "L3-Q-HARD-018",
    "L3-Q-INJ-013", "L3-Q-REF-021", "L3-Q-XHARD-004", "L3-Q-XHARD-005", "L3-Q-XHARD-012",
]

OUT = DATA / "eval_failed.csv"


async def _run(ids: list[str]) -> dict[str, str]:
    sem = asyncio.Semaphore(CONCURRENCY)
    answers: dict[str, str] = {}

    async def work(qid: str):
        async with sem:
            try:
                ans = await aanswer(QMAP[qid])
            except Exception as e:  # noqa: BLE001
                ans = f"(error: {str(e)[:160]})"
            answers[qid] = " ".join(str(ans).split())

    await asyncio.gather(*[work(q) for q in ids])
    return answers


def main() -> int:
    gt = load_ground_truth()
    ids = [q for q in FAILED_SET if q in QMAP]
    print(f"running {len(ids)} previously-failed questions (concurrency={CONCURRENCY})...\n")
    answers = asyncio.run(_run(ids))

    rows = []
    for qid in ids:
        g = gt.get(qid, {})
        conf = str(g.get("confidence", ""))
        ref = str(g.get("answer", ""))
        ag = answers.get(qid, "")
        label, detail = scoring.score(conf, ref, ag)
        rows.append((qid, conf, label, detail, ref, ag))

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "confidence", "score", "detail", "ground_truth", "agent_answer"])
        w.writerows(rows)

    npass = sum(1 for r in rows if r[2] == "PASS")
    print(f"{'id':<16} {'conf':<8} {'score':<7} detail")
    print("-" * 60)
    for qid, conf, label, detail, ref, ag in rows:
        print(f"{qid:<16} {conf:<8} {label:<7} {detail}")
        print(f"   GT : {ref[:110]}")
        print(f"   AG : {ag[:160]}\n")
    print(f"PASS {npass}/{len(rows)}  ->  {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
