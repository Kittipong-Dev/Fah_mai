"""Ingestion step 2 (LEAN, no embeddings): documents -> doc_corpus, BKK-CTW POS logs -> pos_logs.

- doc_corpus: every .md under data/docs/ and data/reports/ (chats flattened from JSONL).
              accessed via metadata filter (channel, doc_date) + ILIKE keyword + get_document.
- pos_logs:   only pos_BKK-CTW_*.tsv (the branch XHARD-012 asks about), v1+v2 unioned.

Run (after `apply_sql.py scripts/setup_docs.sql`):
    uv run python -m fahmai.ingestion.load_docs
"""
from __future__ import annotations

import io
import json
import re

import pandas as pd
from sqlalchemy import types as T

from fahmai.db import ROOT, get_engine

DOCS = ROOT / "data" / "docs"
REPORTS = ROOT / "data" / "reports"
LOGS = ROOT / "data" / "logs"

DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
YM_RE = re.compile(r"(\d{4})-(\d{2})(?!\d)")
HEADING_RE = re.compile(r"^#+\s*(.+)$", re.MULTILINE)
INJ_RE = re.compile(
    r"\[INTERNAL OVERRIDE\]|\[SYSTEM\]|admin mode|system override|ignore (the )?previous"
    r"|disregard|you must now|data not available|พบกันใหม่",
    re.IGNORECASE,
)
FOLDER_CHANNEL = {
    "chat_line_oa": "chat_oa", "chat_line_works": "chat_works",
    "email": "email", "memo": "memo", "minutes": "minutes",
}


def channel_of(rel_parts: tuple[str, ...]) -> str:
    if rel_parts[1] == "reports":
        return "report"
    folder = rel_parts[2]
    if folder == "l1_kb":
        sub = rel_parts[3] if len(rel_parts) > 3 else ""
        return {"policies": "kb_policy", "products": "kb_product", "store_info": "store_info"}.get(sub, "kb")
    return FOLDER_CHANNEL.get(folder, folder)


def doc_date_of(name: str) -> str:
    m = DATE_RE.search(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = YM_RE.search(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    return ""


def topic_of(stem: str) -> str:
    parts = stem.split("__")
    return parts[1] if len(parts) >= 3 else ""


def flatten_jsonl(text: str) -> tuple[str, str]:
    """If JSONL chat -> ('[M-001 10:12 SPEAKER] text'..., 'speakers'); else (text, '')."""
    if not text.lstrip().startswith("{"):
        return text, ""
    lines, speakers = [], []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:  # noqa: BLE001
            lines.append(ln)
            continue
        sp = o.get("speaker", "")
        if sp and sp not in speakers:
            speakers.append(sp)
        lines.append(f"[{o.get('message_id','')} {o.get('timestamp','')} {sp}] {o.get('text','')}".strip())
    return "\n".join(lines), ",".join(speakers)


def title_of(text: str) -> str:
    m = HEADING_RE.search(text)
    if m:
        return m.group(1).strip()[:200]
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first[:200]


def build_rows() -> pd.DataFrame:
    files = list(DOCS.rglob("*.md")) + list(REPORTS.rglob("*.md"))
    rows = []
    for i, p in enumerate(files):
        if i % 10000 == 0 and i:
            print(f"  ...{i:,}/{len(files):,}")
        rel_parts = p.relative_to(ROOT).parts
        raw = p.read_text(encoding="utf-8", errors="replace")
        content, speakers = flatten_jsonl(raw)
        rows.append({
            "doc_id": p.stem,
            "channel": channel_of(rel_parts),
            "doc_date": doc_date_of(p.name),
            "topic": topic_of(p.stem),
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "title": "" if speakers else title_of(raw),
            "participants": speakers,
            "is_adversarial": "true" if INJ_RE.search(content) else "false",
            "content": content,
        })
    print(f"  built {len(rows):,} doc rows")
    return pd.DataFrame(rows)


def copy_df(engine, table: str, df: pd.DataFrame) -> int:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    cols = ", ".join(f'"{c}"' for c in df.columns)
    raw = engine.raw_connection()
    try:
        pg = raw.driver_connection
        with pg.cursor() as cur:
            with cur.copy(f'COPY "{table}" ({cols}) FROM STDIN WITH (FORMAT csv, NULL \'\')') as cp:
                cp.write(buf.getvalue())
            cur.execute(f'SELECT count(*) FROM "{table}"')
            n = cur.fetchone()[0]
        pg.commit()
    finally:
        raw.close()
    return n


# ---- pos_logs (BKK-CTW only) ----
POS_NUM = {"unit_price_thb", "discount_amt", "discount_total_thb"}
POS_INT = {"quantity", "line_seq", "schema_version"}


def pos_col_type(c: str):
    if c in POS_NUM:
        return T.Numeric(14, 2)
    if c in POS_INT:
        return T.Integer()
    return T.Text()


def load_pos(engine) -> int:
    files = sorted(LOGS.glob("pos_BKK-CTW_*.tsv"))
    if not files:
        print("  no BKK-CTW pos files")
        return 0
    frames = []
    for f in files:
        d = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
        d["source_file"] = f.name
        frames.append(d)
    pos = pd.concat(frames, ignore_index=True, sort=False)
    pos.columns = [c.lower() for c in pos.columns]
    dtype_map = {c: pos_col_type(c) for c in pos.columns}
    pos.head(0).to_sql("pos_logs", engine, if_exists="replace", index=False, dtype=dtype_map)
    n = copy_df(engine, "pos_logs", pos)
    print(f"  pos_logs (BKK-CTW): {n:,} rows from {len(files)} files; cols={list(pos.columns)}")
    return n


def main() -> int:
    engine = get_engine()
    print("building doc_corpus rows...")
    df = build_rows()
    print("copying doc_corpus...")
    n = copy_df(engine, "doc_corpus", df)
    print(f"doc_corpus: {n:,} rows")
    print("channel breakdown:\n" + df["channel"].value_counts().to_string())
    print(f"adversarial-flagged: {(df['is_adversarial'] == 'true').sum()}")
    print("\nloading pos_logs...")
    load_pos(engine)
    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
