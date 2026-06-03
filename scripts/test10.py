# -*- coding: utf-8 -*-
"""Ad-hoc test: run the agent on a spread of 10 questions and score vs gt_claude.csv.

Does NOT touch submission.csv. Usage: uv run python scripts/test10.py [id1 id2 ...]
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

import pandas as pd

from fahmai.agents.config import CONCURRENCY, PER_Q_TIMEOUT
from fahmai.agents.data import QMAP
from fahmai.agents.graph import aanswer

ROOT = Path(__file__).resolve().parents[1]
KEY = {str(r.id): str(r.answer) for r in pd.read_csv(ROOT / "gt_claude.csv").fillna("").itertuples()}

ID_RE = re.compile(r"[A-Z]{2,}-[A-Za-z0-9-]+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
REFUSE = ["ไม่พบ", "ไม่มี", "ไม่สามารถ", "ปฏิเสธ", "ไม่ถูกต้อง", "ไม่ปรากฏ"]

DEFAULT_IDS = [
    "L3-Q-EASY-001", "L3-Q-EASY-006", "L3-Q-EASY-011",
    "L3-Q-MED-001", "L3-Q-MED-008",
    "L3-Q-HARD-001", "L3-Q-HARD-002",
    "L3-Q-XHARD-001", "L3-Q-XHARD-002",
    "L3-Q-INJ-001",
]


def norm_num(s):
    s = s.replace(",", "")
    return re.sub(r"\.0+$", "", s)


def key_tokens(text):
    toks = set()
    for m in ID_RE.findall(text):
        toks.add(("id", m.lower()))
    for d in DATE_RE.findall(text):
        toks.add(("date", d))
    masked = ID_RE.sub(" ", DATE_RE.sub(" ", text))
    for n in NUM_RE.findall(masked):
        n2 = norm_num(n)
        if len(n2.replace(".", "")) >= 2:
            toks.add(("num", n2))
    return toks


def hit(tok, resp, resp_l, resp_num):
    kind, val = tok
    if kind == "num":
        return re.search(r"(?<!\d)" + re.escape(val) + r"(?!\d)", resp_num) is not None
    if kind == "id":
        return val in resp_l
    return val in resp


def score(qid, a):
    g = KEY.get(qid, "")
    al, anum = a.lower(), norm_num(a)
    toks = key_tokens(g)
    if not toks:
        label = "MATCH" if (any(m in g for m in REFUSE) == any(m in a for m in REFUSE)) else "MISS"
        return label, 1.0 if label == "MATCH" else 0.0
    h = sum(1 for t in toks if hit(t, a, al, anum))
    frac = h / len(toks)
    return ("MATCH" if frac >= 0.8 else "PARTIAL" if frac >= 0.4 else "MISS"), round(frac, 2)


async def main(ids):
    sem = asyncio.Semaphore(CONCURRENCY)
    results = {}

    async def work(qid):
        async with sem:
            t = time.perf_counter()
            try:
                ans = await asyncio.wait_for(aanswer(QMAP[qid]), timeout=PER_Q_TIMEOUT)
            except asyncio.TimeoutError:
                ans = "(timeout)"
            except Exception as e:  # noqa: BLE001
                ans = f"(error: {str(e)[:160]})"
            ans = " ".join(str(ans).split())
            lab, frac = score(qid, ans)
            results[qid] = (lab, frac, ans, time.perf_counter() - t)
            print(f"  {qid:<16} {lab:<8} {frac:>4}  ({results[qid][3]:.0f}s)")

    print(f"running {len(ids)} questions (concurrency={CONCURRENCY})\n")
    await asyncio.gather(*[work(q) for q in ids])

    print("\n=== results vs gt_claude.csv ===")
    tot = {"MATCH": 0, "PARTIAL": 0, "MISS": 0}
    for qid in ids:
        lab, frac, ans, _ = results[qid]
        tot[lab] += 1
    print(f"MATCH {tot['MATCH']} | PARTIAL {tot['PARTIAL']} | MISS {tot['MISS']}\n")
    for qid in ids:
        lab, frac, ans, _ = results[qid]
        print(f"[{lab:<7} {frac}] {qid}")
        print(f"    gold: {KEY.get(qid, '')[:140]}")
        print(f"    ans : {ans[:140]}\n")


if __name__ == "__main__":
    ids = sys.argv[1:] or DEFAULT_IDS
    ids = [i for i in ids if i in QMAP]
    raise SystemExit(asyncio.run(main(ids)))
