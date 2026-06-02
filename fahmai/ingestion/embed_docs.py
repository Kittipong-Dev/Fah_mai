"""Ingestion step 3 (hybrid): embed doc_corpus -> doc_vec via OpenRouter bge-m3 (halfvec 1024).

Resumable: skips doc_ids already present in doc_vec; COPYs each batch as it finishes
(so a mid-run failure keeps prior progress — just re-run to continue).

Run (after `apply_sql.py scripts/setup_vec.sql`):
    uv run python -m fahmai.ingestion.embed_docs            # full / resume
    uv run python -m fahmai.ingestion.embed_docs --probe 96 # timing probe, no write
"""
from __future__ import annotations

import csv
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import text

from fahmai.db import get_engine
from fahmai.embed import embed_batch

BATCH = 96
WORKERS = 6
MAXCHARS = 12000  # only 7 docs exceed 6000 chars (policies/FAQ, max ~8450); bge-m3 ctx=8192 tok covers them whole — no chunking


def vec_str(v) -> str:
    return "[" + ",".join(f"{x:.5f}" for x in v) + "]"


def append_rows(pg, rows) -> None:
    buf = io.StringIO()
    w = csv.writer(buf)
    for doc_id, v in rows:
        w.writerow([doc_id, v])
    with pg.cursor() as cur:
        with cur.copy("COPY doc_vec (doc_id, embedding) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
            cp.write(buf.getvalue())
    pg.commit()


def main(probe: int | None = None) -> int:
    engine = get_engine()
    with engine.connect() as c:
        rows = c.execute(text("select doc_id, content from doc_corpus")).fetchall()
        done_ids = set() if probe else {r[0] for r in c.execute(text("select doc_id from doc_vec"))}

    items = [(d, (content or " ")[:MAXCHARS] or " ") for d, content in rows if d not in done_ids]
    if probe:
        items = items[:probe]
    batches = [items[i : i + BATCH] for i in range(0, len(items), BATCH)]
    print(f"{len(items):,} to embed ({len(done_ids):,} already done), {len(batches)} batches "
          f"(batch={BATCH}, workers={WORKERS})")
    if not items:
        print("nothing to do.")
        return 0

    def work(batch):
        embs = embed_batch([t for _, t in batch])
        return [(d, vec_str(e)) for (d, _), e in zip(batch, embs)]

    start = time.perf_counter()
    done = 0
    raw = engine.raw_connection()
    try:
        pg = raw.driver_connection
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for res in ex.map(work, batches):
                if not probe:
                    append_rows(pg, res)
                done += len(res)
                if done % 4800 < BATCH:
                    rate = done / max(time.perf_counter() - start, 1e-6)
                    print(f"  ...{done:,}/{len(items):,}  ({rate:.0f} docs/s)")
    finally:
        raw.close()

    elapsed = time.perf_counter() - start
    rate = len(items) / max(elapsed, 1e-6)
    print(f"embedded {done:,} in {elapsed:.1f}s ({rate:.0f} docs/s)")
    if probe:
        print(f"PROBE: est full ~= {len(rows) / max(rate, 1e-6) / 60:.1f} min")
        return 0
    with engine.connect() as c:
        total = c.execute(text("select count(*) from doc_vec")).scalar()
    print(f"doc_vec total: {total:,}")
    return 0


if __name__ == "__main__":
    probe = int(sys.argv[sys.argv.index("--probe") + 1]) if "--probe" in sys.argv else None
    raise SystemExit(main(probe))
