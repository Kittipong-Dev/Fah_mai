# -*- coding: utf-8 -*-
"""Score submission.csv against gt_claude.csv (the independently-derived key).

Per question, extract key tokens from the gt_claude answer — IDs (UPPER-dash), dates,
and significant numbers (>=2 digits, comma-stripped) — and measure how many appear in the
agent's response. Classify MATCH (>=80%) / PARTIAL (40-79%) / MISS (<40%). For text/refusal
answers (no key tokens), check refusal-marker agreement.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sub = {str(r.id): str(r.response) for r in pd.read_csv(ROOT / "submission.csv").fillna("").itertuples()}
key = {str(r.id): str(r.answer) for r in pd.read_csv(ROOT / "gt_claude.csv").fillna("").itertuples()}

ID_RE = re.compile(r"[A-Z]{2,}-[A-Za-z0-9-]+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
REFUSE = ["ไม่พบ", "ไม่มี", "ไม่สามารถ", "ปฏิเสธ", "ไม่ถูกต้อง", "ไม่ปรากฏ"]


def norm_num(s):
    s = s.replace(",", "")
    s = re.sub(r"\.0+$", "", s)  # 42900.00 -> 42900
    return s


def key_tokens(text):
    toks = set()
    for m in ID_RE.findall(text):
        toks.add(("id", m.lower()))
    for d in DATE_RE.findall(text):
        toks.add(("date", d))
    masked = DATE_RE.sub(" ", text)
    masked = ID_RE.sub(" ", masked)
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
    return val in resp  # date


rows = []
cats = {}
for qid in sorted(sub):
    g, a = key[qid], sub[qid]
    al, anum = a.lower(), norm_num(a)
    toks = key_tokens(g)
    cat = qid.split("-")[2]
    cats.setdefault(cat, {"MATCH": 0, "PARTIAL": 0, "MISS": 0})
    if not toks:  # refusal / pure-text key
        g_ref = any(m in g for m in REFUSE)
        a_ref = any(m in a for m in REFUSE)
        label = "MATCH" if (g_ref == a_ref) else "MISS"
        frac = 1.0 if label == "MATCH" else 0.0
    else:
        h = sum(1 for t in toks if hit(t, a, al, anum))
        frac = h / len(toks)
        label = "MATCH" if frac >= 0.8 else ("PARTIAL" if frac >= 0.4 else "MISS")
    cats[cat][label] += 1
    rows.append((qid, label, round(frac, 2)))

tot = {"MATCH": 0, "PARTIAL": 0, "MISS": 0}
for _, lab, _ in rows:
    tot[lab] += 1

print("=== vs gt_claude.csv ===")
print(f"MATCH {tot['MATCH']} | PARTIAL {tot['PARTIAL']} | MISS {tot['MISS']}")
print()
print(f"{'Cat':<7}{'MATCH':>6}{'PARTIAL':>8}{'MISS':>6}")
for c in ["EASY", "MED", "HARD", "XHARD", "REF", "INJ"]:
    if c in cats:
        x = cats[c]
        print(f"{c:<7}{x['MATCH']:>6}{x['PARTIAL']:>8}{x['MISS']:>6}")
print()
print("PARTIAL:", [q for q, l, _ in rows if l == "PARTIAL"])
print("MISS   :", [q for q, l, _ in rows if l == "MISS"])
