# -*- coding: utf-8 -*-
"""Load warranty-form OCR predictions into Postgres as table `ocr_warranty_form`.

Source: data/renders/warranty_form/warranty_form_submission.csv  (artifact_id, pred_json)
  pred_json fields: claim_id, business_event_date, customer_id, sku_id,
                    claim_reason, claim_amount_thb

Notes on the OCR data (profiled 2026-06-02):
  - business_event_date is **Buddhist era** "DD/MM/2567". We keep the raw string in
    `business_event_date_be` and also store a parsed CE `business_event_date` (date)
    so it joins/filters like the rest of the warehouse.
  - claim_amount_thb is empty for every row (the form doesn't render the amount).
  - claim_reason is "defect" for every row.

Run:  uv run python scripts/load_warranty_ocr.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import types as T

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# use the Supabase session pooler (the direct db.<ref> host is IPv6-only / unresolvable here)
os.environ.setdefault("SUPABASE_DB_HOST", "aws-1-ap-southeast-1.pooler.supabase.com")
os.environ.setdefault("SUPABASE_DB_USER", "postgres.mqjpdavcvedkvusedvyu")
os.environ.setdefault("SUPABASE_DB_PORT", "5432")
from fahmai.db import ROOT, get_engine

CSV = ROOT / "data" / "renders" / "warranty_form" / "warranty_form_submission.csv"
TABLE = "ocr_warranty_form"

COLS = ["claim_id", "business_event_date", "customer_id", "sku_id",
        "claim_reason", "claim_amount_thb"]


def claim_id_from_artifact(art_id: str) -> str | None:
    """artifact_id 'WC-<sku>-<YYYYMM>-<DDcustnum>' -> canonical DB claim_id
    'WC-<YYYYMM>-<DDcustnum>' (the format used in fact_warranty_claim.claim_id).
    The OCR-read `claim_id` on the form is in Buddhist-era format and does NOT
    join; this derived key does."""
    parts = (art_id or "").split("-")
    if len(parts) < 3:
        return None
    return f"WC-{parts[-2]}-{parts[-1]}"


def be_to_ce(be: str) -> date | None:
    """'DD/MM/2567' (Buddhist era) -> datetime.date in CE, or None if unparseable."""
    be = (be or "").strip()
    try:
        d, m, y = (int(x) for x in be.split("/"))
        return date(y - 543, m, d)
    except Exception:  # noqa: BLE001
        return None


def build_df() -> pd.DataFrame:
    raw = pd.read_csv(CSV, dtype=str, keep_default_na=False, na_filter=False)
    recs = []
    for art_id, pj in zip(raw["artifact_id"], raw["pred_json"]):
        d = json.loads(pj)
        recs.append({
            "artifact_id": art_id,
            "claim_id_db": claim_id_from_artifact(art_id),
            "claim_id": d.get("claim_id", "").strip() or None,
            "business_event_date": be_to_ce(d.get("business_event_date", "")),
            "business_event_date_be": d.get("business_event_date", "").strip() or None,
            "customer_id": d.get("customer_id", "").strip() or None,
            "sku_id": d.get("sku_id", "").strip() or None,
            "claim_reason": d.get("claim_reason", "").strip() or None,
            "claim_amount_thb": (d.get("claim_amount_thb", "").strip() or None),
        })
    return pd.DataFrame.from_records(recs)


DTYPES = {
    "artifact_id": T.Text(),
    "claim_id_db": T.Text(),
    "claim_id": T.Text(),
    "business_event_date": T.Date(),
    "business_event_date_be": T.Text(),
    "customer_id": T.Text(),
    "sku_id": T.Text(),
    "claim_reason": T.Text(),
    "claim_amount_thb": T.Numeric(14, 2),
}


def main() -> int:
    if not CSV.exists():
        print(f"missing {CSV}", file=sys.stderr)
        return 1
    df = build_df()
    # cast amount to numeric so the empty strings become proper NULLs / numbers
    df["claim_amount_thb"] = pd.to_numeric(df["claim_amount_thb"], errors="coerce")

    engine = get_engine()
    df.to_sql(TABLE, engine, if_exists="replace", index=False,
              dtype=DTYPES, method="multi", chunksize=500)

    with engine.begin() as c:
        from sqlalchemy import text
        n = c.execute(text(f'SELECT count(*) FROM "{TABLE}"')).scalar()
        dmin, dmax = c.execute(
            text(f'SELECT min(business_event_date), max(business_event_date) FROM "{TABLE}"')
        ).one()
        nbad = c.execute(
            text(f'SELECT count(*) FROM "{TABLE}" WHERE business_event_date IS NULL')
        ).scalar()
    print(f"loaded {TABLE}: {n} rows | date range {dmin}..{dmax} | unparsed dates: {nbad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
