"""Ingestion step 1: load data/tables/*.csv into Supabase Postgres with proper types.

Strategy (fast + correct):
  1. read each CSV as raw strings (empty stays '')
  2. CREATE the table empty with column types inferred by NAME CONVENTION
  3. COPY the rows in with FORMAT csv, NULL '' so Postgres casts text -> type and
     empty fields become NULL automatically

Run:  uv run python -m fahmai.ingestion.load_to_supabase
Connection comes from src/fahmai/db.py (.env DATABASE_URL or SUPABASE_DB_* overrides).
"""
from __future__ import annotations

import io
import sys

import pandas as pd
from sqlalchemy import types as T

from fahmai.db import ROOT, get_engine

TABLES_DIR = ROOT / "data" / "tables"

# columns that are dates but don't end in "_date"
DATE_EXTRA = {
    "date_iso", "pay_period_start", "pay_period_end",
    "invoice_period_start", "invoice_period_end",
}
INT_COLS = {
    "quantity", "age", "warranty_months", "coverage_months", "fiscal_year",
    "fiscal_quarter", "day_of_week", "schema_version", "rank", "version_number",
    "closing_units", "points_delta", "resulting_balance_points", "min_co_signers",
}
NUMERIC_COLS = {"value_numeric", "discount_value", "point_multiplier"}

# expected row counts (from initial profiling) for a sanity assert
EXPECTED = {
    "dim_bank_account": 14, "dim_branch": 11, "dim_care_plus_sku_tier": 2,
    "dim_customer": 30000, "dim_date": 731, "dim_department": 9, "dim_employee": 600,
    "dim_policy_version": 12, "dim_position_level": 6, "dim_product": 110,
    "dim_product_recall_history": 3, "dim_promo_campaign": 7, "dim_promo_mechanic": 8,
    "dim_signing_authority_ladder": 7, "dim_vendor": 6, "dim_vendor_contract_version": 22,
    "fact_bank_transaction": 65334, "fact_cs_interaction": 14368,
    "fact_inventory_monthly_snapshot": 26220, "fact_inventory_movement": 310827,
    "fact_loyalty_ledger": 118857, "fact_payroll": 14400, "fact_promo_redemption": 1583,
    "fact_refund_paid": 7134, "fact_return": 7144, "fact_sales": 117105,
    "fact_sales_line_item": 309129, "fact_shipping": 23182, "fact_vendor_payment": 809,
    "fact_warranty_claim": 3973, "t2_doc_inventory": 81,
}


def col_type(col: str):
    c = col.lower()
    if c == "date_be_string":
        return T.Text()
    if c.endswith("_thb"):
        return T.Numeric(14, 2)    
    if c.endswith("_pct") or c.endswith("_coefficient") or c in NUMERIC_COLS:
        return T.Numeric()
    if c.endswith("_timestamp"):
        return T.TIMESTAMP(timezone=True)
    if c.endswith("_date") or c in DATE_EXTRA:
        return T.Date()
    if c.startswith("is_") or c.startswith("uses_") or c == "care_plus_eligible":
        return T.Boolean()
    if c in INT_COLS:
        return T.Integer()
    return T.Text()


def load_one(engine, csv_path) -> tuple[int, int]:
    name = csv_path.stem.lower()
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_filter=False)
    df.columns = [c.lower() for c in df.columns]
    dtype_map = {c: col_type(c) for c in df.columns}

    # 1) create empty typed table
    df.head(0).to_sql(name, engine, if_exists="replace", index=False, dtype=dtype_map)

    # 2) COPY the data (text -> column type, '' -> NULL)
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    cols = ", ".join(f'"{c}"' for c in df.columns)
    copy_sql = f'COPY "{name}" ({cols}) FROM STDIN WITH (FORMAT csv, NULL \'\')'

    raw = engine.raw_connection()
    try:
        pgconn = raw.driver_connection  # psycopg.Connection
        with pgconn.cursor() as cur:
            with cur.copy(copy_sql) as copy:
                copy.write(buf.getvalue())
            cur.execute(f'SELECT count(*) FROM "{name}"')
            n = cur.fetchone()[0]
        pgconn.commit()
    finally:
        raw.close()
    return n, len(df)


def main() -> int:
    files = sorted(TABLES_DIR.glob("*.csv"))
    if not files:
        print(f"no CSVs in {TABLES_DIR}", file=sys.stderr)
        return 1
    engine = get_engine()
    print(f"loading {len(files)} tables into Postgres...\n")
    bad = []
    for f in files:
        name = f.stem.lower()
        try:
            n, src = load_one(engine, f)
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {name}: {str(e).splitlines()[0]}")
            bad.append(name)
            continue
        exp = EXPECTED.get(name)
        flag = "" if exp is None else (" OK" if n == exp else f" !! expected {exp}")
        print(f"  {name:<34} {n:>8,} rows{flag}")
    print("\ndone." if not bad else f"\ndone with {len(bad)} failures: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
