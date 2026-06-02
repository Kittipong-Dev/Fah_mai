# -*- coding: utf-8 -*-
"""Generate an M-Schema (XiYan-SQL style) for the FahMai warehouse → data/mschema.md (for review).

Semi-structured per-table representation that LLMs read better than DDL/prose:
  # Table: name  (note)
  [
    (col:TYPE, PK | -> fk_table.fk_col, nullable, ex:[v1, v2]),
    ...
  ]
  【Foreign keys】 ...

Scope (decided): curated v_* views + dim_* tables + pos_logs + ocr_warranty_form. Raw fact_* are
summarised in one line (each mirrors its v_*). Types/nullability come from information_schema;
example values are sampled live; PK/FK are inferred (no constraints declared in the DB) from a small
curated map + naming convention.

Run:  uv run python scripts/build_mschema.py   ->  data/mschema.md
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text

from fahmai.db import ROOT, get_engine

# A/B toggle: FAHMAI_SCHEMA_RAW=1 emits raw fact_* (no curated views) to test "do views help?"
RAW_MODE = os.getenv("FAHMAI_SCHEMA_RAW", "0").lower() in ("1", "true", "on")
OUT = ROOT / "data" / ("mschema_raw.md" if RAW_MODE else "mschema.md")
EX_K = 3            # example values per column
EX_MAXLEN = 40
EX_SKIP = re.compile(r"content|title|summary|participant|description|^path$|tracking_number", re.I)

# tables to emit (views first — the agent prefers them — then dims, then the no-view tables)
VIEWS = ["v_sales", "v_sales_items", "v_returns", "v_refunds", "v_warranty", "v_inventory",
         "v_inventory_snapshot", "v_loyalty", "v_promo", "v_vendor_payments", "v_bank_txn",
         "v_payroll", "v_cs", "v_shipping"]
DIMS = ["dim_product", "dim_customer", "dim_employee", "dim_branch", "dim_vendor", "dim_date",
        "dim_policy_version", "dim_signing_authority_ladder", "dim_vendor_contract_version",
        "dim_promo_campaign", "dim_promo_mechanic", "dim_product_recall_history", "dim_bank_account",
        "dim_department", "dim_position_level", "dim_care_plus_sku_tier"]
EXTRA = ["pos_logs", "ocr_warranty_form"]
FACTS = ["fact_sales", "fact_sales_line_item", "fact_return", "fact_refund_paid", "fact_warranty_claim",
         "fact_promo_redemption", "fact_inventory_movement", "fact_inventory_monthly_snapshot",
         "fact_loyalty_ledger", "fact_payroll", "fact_cs_interaction", "fact_shipping",
         "fact_bank_transaction", "fact_vendor_payment"]
TABLES = (FACTS if RAW_MODE else VIEWS) + DIMS + EXTRA

NOTES = {
    "v_sales": "1 row/txn, deduped; enriched (branch/customer/fiscal_year_ce)",
    "v_promo": "phantom dup rows share txn_id across channel — dedup by txn_id for 'real' count",
    "dim_policy_version": "as-of: effective_date<=D AND (end_date IS NULL OR end_date>D)",
    "dim_date": "fiscal_year is BUDDHIST ERA; use fiscal_year_ce for CE",
    "ocr_warranty_form": "OCR of warranty_form PNGs; claim_id_db joins fact_warranty_claim.claim_id",
    "pos_logs": "BKK-CTW only; v1->v2 cutover 2025-04-01 (discount_amt -> discount_total_thb)",
}

# inferred PK by table (no constraints in DB)
PRIMARY_KEY = {
    "dim_product": "sku_id", "dim_customer": "customer_id", "dim_employee": "employee_id",
    "dim_branch": "branch_code", "dim_vendor": "vendor_id", "dim_date": "date_iso",
    "dim_policy_version": "policy_version_id", "dim_signing_authority_ladder": "ladder_row_id",
    "dim_vendor_contract_version": "contract_version_id", "dim_promo_campaign": "campaign_id",
    "dim_promo_mechanic": "promo_mechanic_id", "dim_product_recall_history": "history_id",
    "dim_bank_account": "account_id", "dim_department": "dept_code",
    "dim_position_level": "position_level_code", "v_sales": "txn_id", "v_sales_items": "line_item_id",
    "v_returns": "return_id", "v_refunds": "refund_id", "v_warranty": "claim_id",
    "v_inventory": "movement_id", "v_inventory_snapshot": "snapshot_id", "v_loyalty": "ledger_id",
    "v_promo": "redemption_id", "v_vendor_payments": "payment_id", "v_bank_txn": "bank_txn_id",
    "v_payroll": "payroll_id", "v_cs": "cs_interaction_id", "v_shipping": "shipping_id",
    "ocr_warranty_form": "artifact_id",
    # raw fact_* PKs (same id names as their views)
    "fact_sales": "txn_id", "fact_sales_line_item": "line_item_id", "fact_return": "return_id",
    "fact_refund_paid": "refund_id", "fact_warranty_claim": "claim_id",
    "fact_promo_redemption": "redemption_id", "fact_inventory_movement": "movement_id",
    "fact_inventory_monthly_snapshot": "snapshot_id", "fact_loyalty_ledger": "ledger_id",
    "fact_payroll": "payroll_id", "fact_cs_interaction": "cs_interaction_id",
    "fact_shipping": "shipping_id", "fact_bank_transaction": "bank_txn_id",
    "fact_vendor_payment": "payment_id",
}

# curated foreign keys (col on table -> target table.col)
FOREIGN_KEYS = [
    ("v_sales", "customer_id", "dim_customer.customer_id"),
    ("v_sales", "branch_code", "dim_branch.branch_code"),
    ("v_sales", "employee_id", "dim_employee.employee_id"),
    ("v_sales", "promo_campaign_id", "dim_promo_campaign.campaign_id"),
    ("v_sales_items", "sku_id", "dim_product.sku_id"),
    ("v_sales_items", "txn_id", "v_sales.txn_id"),
    ("v_returns", "sku_id", "dim_product.sku_id"),
    ("v_returns", "customer_id", "dim_customer.customer_id"),
    ("v_returns", "original_txn_id", "v_sales.txn_id"),
    ("v_warranty", "sku_id", "dim_product.sku_id"),
    ("v_warranty", "customer_id", "dim_customer.customer_id"),
    ("v_refunds", "approver_employee_id", "dim_employee.employee_id"),
    ("v_vendor_payments", "vendor_id", "dim_vendor.vendor_id"),
    ("v_vendor_payments", "vendor_contract_version_id", "dim_vendor_contract_version.contract_version_id"),
    ("dim_product", "vendor_id", "dim_vendor.vendor_id"),
    ("dim_signing_authority_ladder", "policy_version_id", "dim_policy_version.policy_version_id"),
    ("dim_promo_mechanic", "campaign_id", "dim_promo_campaign.campaign_id"),
    ("dim_product_recall_history", "sku_id", "dim_product.sku_id"),
    ("ocr_warranty_form", "claim_id_db", "v_warranty.claim_id (= fact_warranty_claim.claim_id)"),
    # raw fact_* FKs (for RAW_MODE)
    ("fact_sales", "customer_id", "dim_customer.customer_id"),
    ("fact_sales", "branch_code", "dim_branch.branch_code"),
    ("fact_sales", "employee_id", "dim_employee.employee_id"),
    ("fact_sales", "promo_campaign_id", "dim_promo_campaign.campaign_id"),
    ("fact_sales_line_item", "txn_id", "fact_sales.txn_id"),
    ("fact_sales_line_item", "sku_id", "dim_product.sku_id"),
    ("fact_return", "sku_id", "dim_product.sku_id"),
    ("fact_return", "customer_id", "dim_customer.customer_id"),
    ("fact_return", "original_txn_id", "fact_sales.txn_id"),
    ("fact_refund_paid", "return_id", "fact_return.return_id"),
    ("fact_refund_paid", "approver_employee_id", "dim_employee.employee_id"),
    ("fact_warranty_claim", "sku_id", "dim_product.sku_id"),
    ("fact_warranty_claim", "customer_id", "dim_customer.customer_id"),
    ("fact_promo_redemption", "txn_id", "fact_sales.txn_id"),
    ("fact_promo_redemption", "campaign_id", "dim_promo_campaign.campaign_id"),
    ("fact_inventory_movement", "sku_id", "dim_product.sku_id"),
    ("fact_inventory_movement", "branch_code", "dim_branch.branch_code"),
    ("fact_vendor_payment", "vendor_id", "dim_vendor.vendor_id"),
    ("fact_vendor_payment", "vendor_contract_version_id", "dim_vendor_contract_version.contract_version_id"),
    ("fact_cs_interaction", "customer_id", "dim_customer.customer_id"),
    ("fact_cs_interaction", "employee_id", "dim_employee.employee_id"),
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
    if dt == "double precision" or dt == "real":
        return "FLOAT"
    return dt.upper()


def columns(conn, table: str):
    return conn.execute(text("""
        select column_name, data_type, is_nullable, numeric_precision, numeric_scale
        from information_schema.columns
        where table_schema='public' and table_name=:t order by ordinal_position
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
    engine = get_engine()
    fk_by_col = {(t, c): tgt for t, c, tgt in FOREIGN_KEYS}
    blocks, n_tab, n_col = [], 0, 0
    with engine.connect() as conn:
        for tbl in TABLES:
            cols = columns(conn, tbl)
            if not cols:
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
                # nullable tag omitted: pandas to_sql makes every column nullable -> no signal
                ex = examples(conn, tbl, name)
                ex_s = f", ex:[{', '.join(ex)}]" if ex else ""
                lines.append(f"  ({name}:{', '.join(tags)}{ex_s})")
                n_col += 1
            lines.append("]")
            blocks.append("\n".join(lines))
            n_tab += 1

    tset = set(TABLES)
    fk_lines = [f"{t}.{c} = {tgt}" for t, c, tgt in FOREIGN_KEYS if t in tset]
    if RAW_MODE:
        header = "【DB_ID】 fahmai   (Supabase Postgres — RAW fact_* tables; apply BE→CE + dedup yourself)"
        raw_note = ("\n## Note: curated v_* views also exist (fact_* + enrichment/dedup/fiscal_year_ce);\n"
                    "doc_corpus(doc_id, channel, doc_date, topic, content, ...)")
    else:
        header = "【DB_ID】 fahmai   (Supabase Postgres — prefer the v_* views)"
        raw_note = ("\n## Raw fact_* tables (no M-Schema block — each mirrors its v_* minus enrichment/dedup;\n"
                    "use only for data-quality / phantom / when a question names FACT_* explicitly):\n"
                    "fact_sales, fact_sales_line_item, fact_return, fact_refund_paid, fact_warranty_claim,\n"
                    "fact_promo_redemption, fact_inventory_movement, fact_inventory_monthly_snapshot,\n"
                    "fact_loyalty_ledger, fact_payroll, fact_cs_interaction, fact_shipping, fact_bank_transaction,\n"
                    "fact_vendor_payment, doc_corpus(doc_id, channel, doc_date, topic, content, ...)")

    doc = (header + "\n\n" + "\n\n".join(blocks)
           + "\n\n【Foreign keys】\n" + "\n".join(fk_lines)
           + "\n" + raw_note + "\n")
    OUT.write_text(doc, encoding="utf-8")                       # human-readable review copy
    PY_OUT = ROOT / "fahmai" / "tools" / "mschema.py"           # importable module for schema_card
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
