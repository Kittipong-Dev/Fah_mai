# -*- coding: utf-8 -*-
"""Batch runner + CLI.

  python main.py answer "<question text or question id>"
  python main.py submit [--limit N]      # resumable: fills only blank ids in submission.csv
  python main.py eval                    # regression compare on the previously-failed questions

`submit` is resumable & crash-safe: it reads submission.csv, runs only the still-blank ids
(concurrency from config), and rewrites the full CSV after every completed question.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import time

import pandas as pd

from fahmai.agents.config import CONCURRENCY, PER_Q_TIMEOUT, SUBMISSION_CSV
from fahmai.agents.data import QMAP
from fahmai.agents.graph import aanswer, answer


def _read_results() -> dict[str, str]:
    if SUBMISSION_CSV.exists():
        prev = pd.read_csv(SUBMISSION_CSV).fillna("")
        return {str(r.id): str(r.response) for r in prev.itertuples()}
    return {}


def _write_results(results: dict[str, str]) -> None:
    with SUBMISSION_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "response"])
        for qid in QMAP:
            w.writerow([qid, results.get(qid, "")])


async def run_submission(limit: int | None = None) -> int:
    """Fill blank answers in submission.csv (resumable)."""
    results = _read_results()
    todo = [q for q in QMAP if not str(results.get(q, "")).strip()]
    if limit:
        todo = todo[:limit]
    print(f"{len(QMAP)} total | {len(QMAP) - len(todo)} already done | running {len(todo)} "
          f"(concurrency={CONCURRENCY})")

    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    t0 = time.perf_counter()
    n = {"done": 0}

    async def work(qid: str):
        async with sem:
            t = time.perf_counter()
            try:
                ans = await asyncio.wait_for(aanswer(QMAP[qid]), timeout=PER_Q_TIMEOUT)
            except asyncio.TimeoutError:
                ans = "(timeout)"
            except Exception as e:  # noqa: BLE001
                ans = f"(error: {str(e)[:160]})"
            results[qid] = " ".join(str(ans).split())  # flatten newlines for clean CSV
            async with lock:
                _write_results(results)
                n["done"] += 1
                eta = (time.perf_counter() - t0) / n["done"] * (len(todo) - n["done"]) / 60
                print(f"[{n['done']}/{len(todo)}] {qid} ({time.perf_counter()-t:.0f}s) "
                      f"eta~{eta:.0f}min :: {results[qid][:60]}")

    await asyncio.gather(*[work(q) for q in todo])
    _write_results(results)
    blank = sum(1 for q in QMAP if not str(results.get(q, "")).strip())
    print(f"\ndone -> {SUBMISSION_CSV} ({len(QMAP)-blank}/{len(QMAP)} filled, {blank} blank)")
    return 0


def _resolve_question(arg: str) -> str:
    """Accept either a question id (L3-Q-...) or raw question text."""
    return QMAP.get(arg, arg)


def cli() -> int:
    p = argparse.ArgumentParser(prog="fahmai", description="FahMai team-agent CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("answer", help="answer one question (id or text)")
    pa.add_argument("question")

    ps = sub.add_parser("submit", help="resumable batch -> submission.csv")
    ps.add_argument("--limit", type=int, default=None)

    sub.add_parser("eval", help="regression compare on previously-failed questions")

    args = p.parse_args()
    if args.cmd == "answer":
        print(answer(_resolve_question(args.question)))
        return 0
    if args.cmd == "submit":
        return asyncio.run(run_submission(limit=args.limit))
    if args.cmd == "eval":
        from fahmai.agents.evaluate import main as eval_main
        return eval_main()
    return 1


if __name__ == "__main__":
    raise SystemExit(cli())
