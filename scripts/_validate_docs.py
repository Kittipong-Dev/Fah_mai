# -*- coding: utf-8 -*-
"""Quick UTF-8-safe checks that Thai ILIKE works and key docs are retrievable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fahmai.db import get_engine
from sqlalchemy import text

eng = get_engine()
with eng.connect() as c:
    def q(s, **p):
        return c.execute(text(s), p).fetchall()

    print("Thai ILIKE 'ปรับปรุง' across all docs:",
          q("select count(*) from doc_corpus where content ilike :k", k="%ปรับปรุง%")[0][0])
    print("Thai ILIKE 'รับประกัน' (warranty) in kb_product:",
          q("select count(*) from doc_corpus where channel='kb_product' and content ilike :k", k="%รับประกัน%")[0][0])

    print("\nREF-023 minutes MIN-OPS-2025-04 present:",
          q("select doc_id, doc_date from doc_corpus where doc_id ilike :k", k="%MIN-OPS-2025-04%"))

    print("\nREF-008: V-007 name from dim_vendor:")
    v = q("select vendor_id, name_th, name_en from dim_vendor where vendor_id='V-007'")
    print("  ", v)
    if v:
        for col in (v[0][1], v[0][2]):
            if col:
                n = q("select count(*) from doc_corpus where channel='email' and content ilike :k",
                      k=f"%{col}%")[0][0]
                print(f"  emails mentioning '{col}': {n}")

    print("\nKB product mentioning 'Powercell X3' (chat_oa, XHARD-015):",
          q("select count(*) from doc_corpus where channel='chat_oa' and content ilike :k", k="%Powercell X3%")[0][0])
