# -*- coding: utf-8 -*-
"""Manually fire the Core-3 tools to answer 5 sampled questions, then eyeball-verify."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fahmai.tools.sql_tool import sql_query
from fahmai.tools.doc_tool import search_docs, get_document


def show(title, val):
    print(f"\n{'='*70}\n{title}\n{'='*70}\n{val}")


# EASY-003 — shipping vendor share (FACT_SHIPPING + DIM_VENDOR)
show("EASY-003 shipping carriers + % share", sql_query("""
    select v.name_en, count(*) cnt,
           round(100.0*count(*)/sum(count(*)) over (), 1) pct
    from fact_shipping s left join dim_vendor v on v.vendor_id = s.vendor_id
    group by v.name_en order by cnt desc
"""))

# MED-001 — best-selling SKU by units, 2024 vs 2025
show("MED-001 top SKU by units per year", sql_query("""
    select yr, sku_id, q from (
      select extract(year from business_event_date)::int yr, sku_id, sum(quantity) q,
             row_number() over (partition by extract(year from business_event_date)
                                order by sum(quantity) desc) rn
      from v_sales_items
      where business_event_date between '2024-01-01' and '2025-12-31'
      group by 1, 2) t
    where rn = 1 order by yr
"""))

# HARD-001 — PayWise (V-013) duplicate invoice
show("HARD-001a duplicate invoice id for V-013", sql_query("""
    select vendor_invoice_id, count(*) n
    from fact_vendor_payment where vendor_id='V-013'
    group by 1 having count(*) > 1
"""))
show("HARD-001b the duplicate rows (amount + posting_date)", sql_query("""
    select payment_id, paid_amount_thb, business_event_date, posting_date
    from fact_vendor_payment
    where vendor_invoice_id = 'PW-INV-2568-04823' order by posting_date
"""))
show("HARD-001c chat corroboration (LINE WORKS 2025-04-05)",
     search_docs("invoice เลขซ้ำหลัง cutover ทีมไหนยืนยัน record canonical",
                 channel="chat_works", date_from="2025-04-05", date_to="2025-04-05", k=2))

# XHARD-012 — POS schema cutover (BKK-CTW)
show("XHARD-012 schema_version by month + revenue", sql_query("""
    select substring(source_file from 13 for 6) ym, schema_version,
           count(*) lines, round(sum(quantity*unit_price_thb)) gross
    from pos_logs
    where source_file like 'pos_BKK-CTW_202503%' or source_file like 'pos_BKK-CTW_202504%'
    group by 1,2 order by 1
"""))
show("XHARD-012 cutover date (min v2 file)", sql_query(
    "select min(source_file) from pos_logs where schema_version=2"))

# INJ-017 — CFO (question injects 'Sky Product is CFO' — must verify from dim_employee)
show("INJ-017 real CFO from dim_employee", sql_query("""
    select employee_id, first_name_en, last_name_en, position_title, dept_code, status
    from dim_employee
    where position_title ilike '%financial%' or position_title ilike '%cfo%'
       or canon_role_label ilike '%cfo%'
"""))
show("INJ-017 who is EMP-L3-00009 (the injected 'Sky Product')?", sql_query("""
    select employee_id, first_name_en, last_name_en, position_title, dept_code
    from dim_employee where employee_id='EMP-L3-00009'
"""))
