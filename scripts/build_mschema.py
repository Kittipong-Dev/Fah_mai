# -*- coding: utf-8 -*-
"""Generate an M-Schema (XiYan-SQL style) for the FahMai grading DB → data/mschema.md (for review).

Semi-structured per-table representation that LLMs read better than DDL/prose:
  # Table: name  (note)
  [
    (col:TYPE, PK | -> fk_table.fk_col, nullable, ex:[v1, v2]),
    ...
  ]
  【Foreign keys】 ...

Scope: the 8 fah_sai_lpk_model views (360/event/catalog) + fah_sai_lpk_core dim_* tables.
Types/nullability come from information_schema; example values are sampled live;
PK/FK are inferred (no constraints declared in DB) from a small curated map + naming convention.

Run:  uv run python scripts/build_mschema.py   ->  data/mschema.md
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text

from fahmai.db import ROOT, get_sql_engine

OUT = ROOT / "data" / "mschema.md"
EX_K = 3
EX_MAXLEN = 40
EX_SKIP = re.compile(
    r"content|title|summary|participant|description|^path$|tracking_number"
    r"|chunk_text|search_tsv|attributes|_metadata|recall_history$",
    re.I,
)

# --- tables to emit ----------------------------------------------------------
# Model-layer 360/event/catalog views (fah_sai_lpk_model schema)
VIEWS = [
    "sales_order_360",
    "sales_line_360",
    "finance_event",
    "customer_ops_event",
    "inventory_event",
    "policy_catalog",
    "product_catalog",
    "document_evidence",
]

# Core dimension tables (fah_sai_lpk_core schema)
DIMS = [
    "dim_product", "dim_customer", "dim_employee", "dim_branch", "dim_vendor", "dim_date",
    "dim_policy_version", "dim_signing_authority_ladder", "dim_vendor_contract_version",
    "dim_promo_campaign", "dim_promo_mechanic", "dim_product_recall_history", "dim_bank_account",
    "dim_department", "dim_position_level", "dim_care_plus_sku_tier",
]

EXTRA: list[str] = []   # pos_logs / ocr_warranty_form live in Supabase, not grading DB

TABLES = VIEWS + DIMS + EXTRA

NOTES = {
    "sales_order_360":      "1 row/txn; basket_total/discount/net in _thb; no fiscal_year_ce — derive from business_event_date",
    "sales_line_360":       "line items; join to sales_order_360 on txn_id",
    "finance_event":        "UNION bank_txns+refunds+vendor_payments+payroll; event_type discriminates; amount_direction: credit/debit",
    "customer_ops_event":   "UNION returns+refunds+warranty+cs+shipping+loyalty+promo; event_type discriminates",
    "inventory_event":      "UNION movements+monthly_snapshots; event_type discriminates; closing_units from snapshots",
    "policy_catalog":       "UNION policy_version+promo+vendor_contract+signing_ladder; effective_date/end_date as-of filter applies",
    "product_catalog":      "dim_product enriched with vendor name, care_plus tiers, recall history",
    "document_evidence":    "RAG/doc chunks; source_kind e.g. 'doc_chat_line_oa'; for chat/doc counts+keywords use SQL here",
    "dim_date":             "fiscal_year is BUDDHIST ERA; use fiscal_year_ce for CE",
    "dim_policy_version":   "as-of: effective_date<=D AND (end_date IS NULL OR end_date>D)",
}

# inferred PK by table (no DB constraints)
PRIMARY_KEY = {
    # model views
    "sales_order_360":    "txn_id",
    "sales_line_360":     "line_item_id",
    "finance_event":      "event_id",
    "customer_ops_event": "event_id",
    "inventory_event":    "event_id",
    "policy_catalog":     None,          # composite — no single PK
    "product_catalog":    "sku_id",
    "document_evidence":  "chunk_id",
    # core dims
    "dim_product":                  "sku_id",
    "dim_customer":                 "customer_id",
    "dim_employee":                 "employee_id",
    "dim_branch":                   "branch_code",
    "dim_vendor":                   "vendor_id",
    "dim_date":                     "date_iso",
    "dim_policy_version":           "policy_version_id",
    "dim_signing_authority_ladder": "ladder_row_id",
    "dim_vendor_contract_version":  "contract_version_id",
    "dim_promo_campaign":           "campaign_id",
    "dim_promo_mechanic":           "promo_mechanic_id",
    "dim_product_recall_history":   "history_id",
    "dim_bank_account":             "account_id",
    "dim_department":               "dept_code",
    "dim_position_level":           "position_level_code",
    "dim_care_plus_sku_tier":       "sku_tier_id",
}

# curated foreign keys (table, col) -> target string
FOREIGN_KEYS = [
    # sales_order_360
    ("sales_order_360", "customer_id",       "dim_customer.customer_id"),
    ("sales_order_360", "branch_code",       "dim_branch.branch_code"),
    ("sales_order_360", "employee_id",       "dim_employee.employee_id"),
    ("sales_order_360", "promo_campaign_id", "dim_promo_campaign.campaign_id"),
    # sales_line_360
    ("sales_line_360",  "txn_id",   "sales_order_360.txn_id"),
    ("sales_line_360",  "sku_id",   "dim_product.sku_id"),
    ("sales_line_360",  "vendor_id","dim_vendor.vendor_id"),
    # finance_event
    ("finance_event", "vendor_id",           "dim_vendor.vendor_id"),
    ("finance_event", "employee_id",         "dim_employee.employee_id"),
    ("finance_event", "approver_employee_id","dim_employee.employee_id"),
    ("finance_event", "account_id",          "dim_bank_account.account_id"),
    # customer_ops_event
    ("customer_ops_event", "customer_id", "dim_customer.customer_id"),
    ("customer_ops_event", "txn_id",      "sales_order_360.txn_id"),
    ("customer_ops_event", "sku_id",      "dim_product.sku_id"),
    ("customer_ops_event", "campaign_id", "dim_promo_campaign.campaign_id"),
    # inventory_event
    ("inventory_event", "sku_id",      "dim_product.sku_id"),
    ("inventory_event", "branch_code", "dim_branch.branch_code"),
    # product_catalog
    ("product_catalog", "vendor_id", "dim_vendor.vendor_id"),
    # dim_* standard
    ("dim_product",                  "vendor_id",         "dim_vendor.vendor_id"),
    ("dim_signing_authority_ladder", "policy_version_id", "dim_policy_version.policy_version_id"),
    ("dim_promo_mechanic",           "campaign_id",       "dim_promo_campaign.campaign_id"),
    ("dim_product_recall_history",   "sku_id",            "dim_product.sku_id"),
]


def short_type(data_type: str, numeric_precision, numeric_scale) -> str:
    dt = data_type.lower()
    if dt in ("text", "character varying", "varchar", "character", "char"):
        return "TEXT"
    if dt == "numeric":
        if numeric_precision and numeric_scale is not None:
            return f"NUMERIC({numeric_precision},{numeric_scale})"
        return "NUMERIC"
    if dt in ("integer", "bigint", "smallint"):
        return "INT"
    if dt == "boolean":
        return "BOOL"
    if dt == "date":
        return "DATE"
    if dt.startswith("timestamp"):
        return "TIMESTAMP"
    if dt in ("double precision", "real"):
        return "FLOAT"
    if dt == "jsonb" or dt == "json":
        return "JSONB"
    return dt.upper()


def columns(conn, table: str):
    return conn.execute(text("""
        select column_name, data_type, is_nullable, numeric_precision, numeric_scale
        from information_schema.columns
        where table_schema IN ('fah_sai_lpk_model','fah_sai_lpk_core')
          and table_name = :t
        order by ordinal_position
    """), {"t": table}).fetchall()


def examples(conn, table: str, col: str) -> list[str]:
    if EX_SKIP.search(col):
        return []
    try:
        rows = conn.execute(text(
            f'select distinct "{col}" from "{table}" where "{col}" is not null limit {EX_K}'
        )).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        v = str(r[0])
        out.append(v if len(v) <= EX_MAXLEN else v[:EX_MAXLEN] + "…")
    return out


def main() -> int:
    engine = get_sql_engine()
    fk_by_col = {(t, c): tgt for t, c, tgt in FOREIGN_KEYS}
    blocks, n_tab, n_col = [], 0, 0
    with engine.connect() as conn:
        for tbl in TABLES:
            cols = columns(conn, tbl)
            if not cols:
                print(f"  [SKIP] {tbl} — no columns found (not in grading DB?)", file=sys.stderr)
                continue
            pk = PRIMARY_KEY.get(tbl)
            note = f"  ({NOTES[tbl]})" if tbl in NOTES else ""
            lines = [f"# Table: {tbl}{note}", "["]
            for name, dtype, nullable, nprec, nscale in cols:
                tags = [short_type(dtype, nprec, nscale)]
                if name == pk:
                    tags.append("PK")
                if (tbl, name) in fk_by_col:
                    tags.append(f"-> {fk_by_col[(tbl, name)]}")
                ex = examples(conn, tbl, name)
                ex_s = f", ex:[{', '.join(ex)}]" if ex else ""
                lines.append(f"  ({name}:{', '.join(tags)}{ex_s})")
                n_col += 1
            lines.append("]")
            blocks.append("\n".join(lines))
            n_tab += 1

    tset = set(TABLES)
    fk_lines = [f"{t}.{c} = {tgt}" for t, c, tgt in FOREIGN_KEYS if t in tset]

    header = (
        "【DB_ID】 fahmai   (Postgres grading DB — schemas fah_sai_lpk_model + fah_sai_lpk_core)\n"
        "# Prefer the 360/event/catalog views (fah_sai_lpk_model) over raw fact_* tables.\n"
        "# fah_sai_lpk_mart views (v_sales_line, v_sales_order, v_vendor_payment, …) also exist\n"
        "# but are NOT on the search_path — qualify with schema or use the model views instead."
    )

    raw_note = (
        "\n## Raw fact_* tables (fah_sai_lpk_core — no M-Schema block):\n"
        "fact_sales, fact_sales_line_item, fact_return, fact_refund_paid, fact_warranty_claim,\n"
        "fact_promo_redemption, fact_inventory_movement, fact_inventory_monthly_snapshot,\n"
        "fact_loyalty_ledger, fact_payroll, fact_cs_interaction, fact_shipping,\n"
        "fact_bank_transaction, fact_vendor_payment\n"
        "(Use only when a question names FACT_* explicitly or for data-quality checks.)\n"
    )

    doc = (header + "\n\n" + "\n\n".join(blocks)
           + "\n\n【Foreign keys】\n" + "\n".join(fk_lines)
           + "\n" + raw_note + "\n")
    OUT.write_text(doc, encoding="utf-8")
    PY_OUT = ROOT / "fahmai" / "tools" / "mschema.py"
    PY_OUT.write_text(
        "# -*- coding: utf-8 -*-\n"
        '"""Auto-generated by scripts/build_mschema.py — do not edit by hand."""\n\n'
        "MSCHEMA = r'''" + doc + "'''\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} + {PY_OUT}: {n_tab} tables, {n_col} columns, {len(doc)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
