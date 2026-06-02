# -*- coding: utf-8 -*-
"""Validate semantic (vector) retrieval over doc_corpus+doc_vec."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from fahmai.db import get_engine
from fahmai.embed import embed_batch

QUERIES = [
    ("นโยบายคืนสินค้าได้ภายในกี่วัน เงื่อนไขอะไรบ้าง", None),
    ("จอมอนิเตอร์ใช้กับ Mini PC ดาวเหนือได้ไหม", "kb_product"),
    ("ลูกค้าบ่นเรื่องแบตเตอรี่ Powercell X3 เสื่อมเร็ว", "chat_oa"),
    ("invoice ของ PayWise ออกเลขซ้ำกันหลัง schema cutover", "chat_works"),
]

eng = get_engine()
with eng.connect() as c:
    sz = c.execute(text("select pg_size_pretty(pg_database_size(current_database()))")).scalar()
    print("DB size now:", sz, "\n")
    for query, chan in QUERIES:
        q = "[" + ",".join(f"{x:.5f}" for x in embed_batch([query])[0]) + "]"
        filt = f"where dc.channel='{chan}'" if chan else ""
        rows = c.execute(text(f"""
            select dc.doc_id, dc.channel, round((1-(dv.embedding <=> cast(:q as halfvec)))::numeric,3) sim
            from doc_corpus dc join doc_vec dv using(doc_id)
            {filt}
            order by dv.embedding <=> cast(:q as halfvec) limit 4
        """), {"q": q}).fetchall()
        print(f"Q: {query[:50]}  [{chan or 'all'}]")
        for r in rows:
            print(f"   {r[2]}  {r[1]:11} {r[0]}")
        print()
