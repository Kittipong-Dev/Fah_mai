# -*- coding: utf-8 -*-
"""Run the current enterprise agent and compare answers to local ground_truth.

Examples:
  python main.py eval
  python main.py eval --id L3-Q-MED-005 --id L3-Q-HARD-003
  python main.py eval --all
  python main.py eval --gt data/ground_truth_opus.csv

The PASS/FAIL/REVIEW label is a local heuristic from fahmai.utils.scoring, not the official grader.
This command writes an eval CSV and never mutates submission.csv.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from fahmai.agents.config import CONCURRENCY, DATA
from fahmai.agents.data import QMAP, load_ground_truth
from fahmai.agents.enterprise_graph import aanswer
from fahmai.utils import scoring

SMOKE_SET = [
    "L3-Q-EASY-002",
    "L3-Q-MED-001",
    "L3-Q-MED-005",
    "L3-Q-HARD-003",
    "L3-Q-XHARD-020",
    "L3-Q-INJ-013",
    "L3-Q-INJ-022",
    "L3-Q-HARD-018",
    "L3-Q-XHARD-004",
    "L3-Q-XHARD-005",
]

OUT = DATA / "eval_current.csv"


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


def _select_ids(ids: list[str] | None = None, limit: int | None = None, all_questions: bool = False) -> list[str]:
    if ids:
        selected: list[str] = []
        for qid in ids:
            selected.extend(part.strip() for part in qid.split(",") if part.strip())
    elif all_questions:
        selected = list(QMAP)
    else:
        selected = list(SMOKE_SET)
    selected = [qid for qid in dict.fromkeys(selected) if qid in QMAP]
    if limit is not None:
        selected = selected[:limit]
    return selected


def main(
    ids: list[str] | None = None,
    limit: int | None = None,
    all_questions: bool = False,
    out: str | Path | None = None,
    gt: str | Path | None = None,
) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    gt_rows = load_ground_truth(gt)
    selected = _select_ids(ids=ids, limit=limit, all_questions=all_questions)
    out_path = Path(out) if out else OUT
    gt_label = str(gt) if gt else "default"
    print(f"running {len(selected)} current-enterprise eval questions (concurrency={CONCURRENCY}, gt={gt_label})...\n")
    answers = asyncio.run(_run(selected))

    rows = []
    for qid in selected:
        g = gt_rows.get(qid, {})
        conf = str(g.get("confidence", ""))
        ref = str(g.get("answer", ""))
        ag = answers.get(qid, "")
        label, detail = scoring.score(conf, ref, ag)
        rows.append((qid, conf, label, detail, ref, ag))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
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
    print(f"PASS {npass}/{len(rows)}  ->  {out_path}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="python -m fahmai.agents.evaluate")
    p.add_argument("--id", action="append", dest="ids", help="Question id; can be repeated or comma-separated")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--all", action="store_true", dest="all_questions")
    p.add_argument("--out", default=None)
    p.add_argument("--gt", default=None, help="Ground-truth CSV path; supports repo or Opus schema")
    args = p.parse_args()
    raise SystemExit(main(ids=args.ids, limit=args.limit, all_questions=args.all_questions, out=args.out, gt=args.gt))
