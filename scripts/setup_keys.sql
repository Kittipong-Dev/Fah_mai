-- Indexes + derived columns + curated views for the FahMai warehouse.
-- No PK/FK constraints (data has intentional retry dups, phantoms, nullable FKs).
-- Idempotent: safe to re-run.

-- ============ derived: CE fiscal year on dim_date (fiscal_year is Buddhist Era) ============
ALTER TABLE dim_date ADD COLUMN IF NOT EXISTS fiscal_year_ce int;
UPDATE dim_date SET fiscal_year_ce = fiscal_year - 543 WHERE fiscal_year IS NOT NULL;

-- ============ indexes on join keys + date filters ============
CREATE INDEX IF NOT EXISTS ix_sales_customer   ON fact_sales (customer_id);
CREATE INDEX IF NOT EXISTS ix_sales_branch     ON fact_sales (branch_code);
CREATE INDEX IF NOT EXISTS ix_sales_employee   ON fact_sales (employee_id);
CREATE INDEX IF NOT EXISTS ix_sales_campaign   ON fact_sales (promo_campaign_id);
CREATE INDEX IF NOT EXISTS ix_sales_bed        ON fact_sales (business_event_date);
CREATE INDEX IF NOT EXISTS ix_sales_txn        ON fact_sales (txn_id);

CREATE INDEX IF NOT EXISTS ix_li_txn           ON fact_sales_line_item (txn_id);
CREATE INDEX IF NOT EXISTS ix_li_sku           ON fact_sales_line_item (sku_id);
CREATE INDEX IF NOT EXISTS ix_li_bed           ON fact_sales_line_item (business_event_date);

CREATE INDEX IF NOT EXISTS ix_bank_account     ON fact_bank_transaction (account_id);
CREATE INDEX IF NOT EXISTS ix_bank_type        ON fact_bank_transaction (transaction_type);
CREATE INDEX IF NOT EXISTS ix_bank_bed         ON fact_bank_transaction (business_event_date);

CREATE INDEX IF NOT EXISTS ix_return_sku       ON fact_return (sku_id);
CREATE INDEX IF NOT EXISTS ix_return_branch    ON fact_return (branch_code);
CREATE INDEX IF NOT EXISTS ix_return_customer  ON fact_return (customer_id);
CREATE INDEX IF NOT EXISTS ix_return_bed       ON fact_return (business_event_date);

CREATE INDEX IF NOT EXISTS ix_refund_approver  ON fact_refund_paid (approver_employee_id);
CREATE INDEX IF NOT EXISTS ix_refund_return    ON fact_refund_paid (return_id);
CREATE INDEX IF NOT EXISTS ix_refund_bed       ON fact_refund_paid (business_event_date);

CREATE INDEX IF NOT EXISTS ix_warranty_sku     ON fact_warranty_claim (sku_id);
CREATE INDEX IF NOT EXISTS ix_warranty_cust    ON fact_warranty_claim (customer_id);
CREATE INDEX IF NOT EXISTS ix_warranty_bed     ON fact_warranty_claim (business_event_date);

CREATE INDEX IF NOT EXISTS ix_vpay_vendor      ON fact_vendor_payment (vendor_id);
CREATE INDEX IF NOT EXISTS ix_vpay_invoice     ON fact_vendor_payment (vendor_invoice_id);
CREATE INDEX IF NOT EXISTS ix_vpay_bed         ON fact_vendor_payment (business_event_date);

CREATE INDEX IF NOT EXISTS ix_promo_campaign   ON fact_promo_redemption (campaign_id);
CREATE INDEX IF NOT EXISTS ix_promo_txn        ON fact_promo_redemption (txn_id);
CREATE INDEX IF NOT EXISTS ix_promo_bed        ON fact_promo_redemption (business_event_date);

CREATE INDEX IF NOT EXISTS ix_invmov_sku       ON fact_inventory_movement (sku_id);
CREATE INDEX IF NOT EXISTS ix_invmov_branch    ON fact_inventory_movement (branch_code);
CREATE INDEX IF NOT EXISTS ix_invmov_type      ON fact_inventory_movement (movement_type);
CREATE INDEX IF NOT EXISTS ix_invmov_bed       ON fact_inventory_movement (business_event_date);

CREATE INDEX IF NOT EXISTS ix_invsnap_sku      ON fact_inventory_monthly_snapshot (sku_id);
CREATE INDEX IF NOT EXISTS ix_invsnap_branch   ON fact_inventory_monthly_snapshot (branch_code);
CREATE INDEX IF NOT EXISTS ix_invsnap_bed      ON fact_inventory_monthly_snapshot (business_event_date);

CREATE INDEX IF NOT EXISTS ix_loyalty_cust     ON fact_loyalty_ledger (customer_id);
CREATE INDEX IF NOT EXISTS ix_loyalty_event    ON fact_loyalty_ledger (event_type);
CREATE INDEX IF NOT EXISTS ix_loyalty_bed      ON fact_loyalty_ledger (business_event_date);

CREATE INDEX IF NOT EXISTS ix_cs_employee      ON fact_cs_interaction (employee_id);
CREATE INDEX IF NOT EXISTS ix_cs_customer      ON fact_cs_interaction (customer_id);
CREATE INDEX IF NOT EXISTS ix_cs_bed           ON fact_cs_interaction (business_event_date);

CREATE INDEX IF NOT EXISTS ix_ship_vendor      ON fact_shipping (vendor_id);
CREATE INDEX IF NOT EXISTS ix_ship_bed         ON fact_shipping (business_event_date);

CREATE INDEX IF NOT EXISTS ix_emp_branch       ON dim_employee (branch_code);
CREATE INDEX IF NOT EXISTS ix_emp_dept         ON dim_employee (dept_code);
CREATE INDEX IF NOT EXISTS ix_emp_poslevel     ON dim_employee (position_level);
CREATE INDEX IF NOT EXISTS ix_prod_vendor      ON dim_product (vendor_id);
CREATE INDEX IF NOT EXISTS ix_cust_type        ON dim_customer (customer_type);
CREATE INDEX IF NOT EXISTS ix_cust_tier        ON dim_customer (loyalty_tier);

-- ============ curated views (agent's primary text-to-SQL surface) ============

-- one row per txn_id: dedup retry rows (latest posting_date, prefer settled), enriched
CREATE OR REPLACE VIEW v_sales AS
SELECT s.*, d.fiscal_year, d.fiscal_year_ce, d.fiscal_quarter,
       b.name_en AS branch_name_en, b.branch_type,
       c.customer_type, c.region AS customer_region, c.loyalty_tier, c.account_manager_id
FROM (
    SELECT DISTINCT ON (txn_id) *
    FROM fact_sales
    ORDER BY txn_id, posting_date DESC NULLS LAST, settlement_bank_txn_id NULLS LAST
) s
LEFT JOIN dim_date d     ON d.date_iso = s.business_event_date
LEFT JOIN dim_branch b   ON b.branch_code = s.branch_code
LEFT JOIN dim_customer c ON c.customer_id = s.customer_id;

-- line items enriched with product + parent-sale context (branch/customer/b2b/promo) + fiscal
CREATE OR REPLACE VIEW v_sales_items AS
SELECT li.*, p.brand_family, p.category, p.subcategory, p.msrp_thb, p.vendor_id AS product_vendor_id,
       s.branch_code, s.customer_id, s.is_b2b, s.promo_campaign_id,
       d.fiscal_year_ce, d.fiscal_quarter
FROM fact_sales_line_item li
LEFT JOIN dim_product p ON p.sku_id = li.sku_id
LEFT JOIN v_sales s     ON s.txn_id = li.txn_id
LEFT JOIN dim_date d    ON d.date_iso = li.business_event_date;

-- returns joined to refunds + product/branch/customer + fiscal
CREATE OR REPLACE VIEW v_returns AS
SELECT r.*, rf.refund_id, rf.refund_amount_thb, rf.approver_employee_id AS refund_approver_id,
       rf.cosig_employee_id AS refund_cosig_id,
       p.brand_family, p.category, b.name_en AS branch_name_en,
       c.customer_type, d.fiscal_year_ce
FROM fact_return r
LEFT JOIN fact_refund_paid rf ON rf.return_id = r.return_id
LEFT JOIN dim_product p   ON p.sku_id = r.sku_id
LEFT JOIN dim_branch b    ON b.branch_code = r.branch_code
LEFT JOIN dim_customer c  ON c.customer_id = r.customer_id
LEFT JOIN dim_date d      ON d.date_iso = r.business_event_date;

-- refunds enriched with approver identity/level (for authority audits)
CREATE OR REPLACE VIEW v_refunds AS
SELECT rf.*, e.first_name_en AS approver_first_en, e.last_name_en AS approver_last_en,
       e.position_level AS approver_position_level, e.dept_code AS approver_dept_code,
       e.position_title AS approver_position_title,
       c.customer_type, d.fiscal_year_ce
FROM fact_refund_paid rf
LEFT JOIN dim_employee e ON e.employee_id = rf.approver_employee_id
LEFT JOIN dim_customer c ON c.customer_id = rf.customer_id
LEFT JOIN dim_date d     ON d.date_iso = rf.business_event_date;

CREATE OR REPLACE VIEW v_warranty AS
SELECT w.*, p.brand_family, p.category, p.msrp_thb, p.warranty_months,
       c.customer_type, d.fiscal_year_ce
FROM fact_warranty_claim w
LEFT JOIN dim_product p  ON p.sku_id = w.sku_id
LEFT JOIN dim_customer c ON c.customer_id = w.customer_id
LEFT JOIN dim_date d     ON d.date_iso = w.business_event_date;

CREATE OR REPLACE VIEW v_inventory AS
SELECT m.*, p.brand_family, p.category, p.end_of_life_date, b.name_en AS branch_name_en,
       d.fiscal_year_ce
FROM fact_inventory_movement m
LEFT JOIN dim_product p ON p.sku_id = m.sku_id
LEFT JOIN dim_branch b  ON b.branch_code = m.branch_code
LEFT JOIN dim_date d    ON d.date_iso = m.business_event_date;

CREATE OR REPLACE VIEW v_inventory_snapshot AS
SELECT s.*, p.brand_family, p.category, p.end_of_life_date, b.name_en AS branch_name_en
FROM fact_inventory_monthly_snapshot s
LEFT JOIN dim_product p ON p.sku_id = s.sku_id
LEFT JOIN dim_branch b  ON b.branch_code = s.branch_code;

CREATE OR REPLACE VIEW v_loyalty AS
SELECT l.*, c.customer_type, c.loyalty_tier AS current_tier, c.region
FROM fact_loyalty_ledger l
LEFT JOIN dim_customer c ON c.customer_id = l.customer_id;

CREATE OR REPLACE VIEW v_promo AS
SELECT pr.*, pc.description_en, pc.start_timestamp, pc.end_timestamp,
       pm.discount_type, pm.discount_value, pm.point_multiplier
FROM fact_promo_redemption pr
LEFT JOIN dim_promo_campaign pc ON pc.campaign_id = pr.campaign_id
LEFT JOIN dim_promo_mechanic pm ON pm.campaign_id = pr.campaign_id;

CREATE OR REPLACE VIEW v_vendor_payments AS
SELECT vp.*, v.name_en AS vendor_name_en, v.category AS vendor_category,
       cv.version_number AS contract_version_number, cv.amendment_summary
FROM fact_vendor_payment vp
LEFT JOIN dim_vendor v ON v.vendor_id = vp.vendor_id
LEFT JOIN dim_vendor_contract_version cv ON cv.contract_version_id = vp.vendor_contract_version_id;

CREATE OR REPLACE VIEW v_bank_txn AS
SELECT bt.*, ba.bank, ba.account_role, ba.associated_branch_code
FROM fact_bank_transaction bt
LEFT JOIN dim_bank_account ba ON ba.account_id = bt.account_id;

CREATE OR REPLACE VIEW v_payroll AS
SELECT pay.*, e.first_name_en, e.last_name_en, e.dept_code, e.position_level,
       e.branch_code, e.position_title
FROM fact_payroll pay
LEFT JOIN dim_employee e ON e.employee_id = pay.employee_id;

CREATE OR REPLACE VIEW v_cs AS
SELECT cs.*, e.first_name_en AS emp_first_en, e.last_name_en AS emp_last_en, e.dept_code AS emp_dept_code,
       c.customer_type, b.name_en AS branch_name_en
FROM fact_cs_interaction cs
LEFT JOIN dim_employee e  ON e.employee_id = cs.employee_id
LEFT JOIN dim_customer c  ON c.customer_id = cs.customer_id
LEFT JOIN dim_branch b    ON b.branch_code = cs.branch_code;

CREATE OR REPLACE VIEW v_shipping AS
SELECT sh.*, v.name_en AS vendor_name_en, b.name_en AS origin_branch_name_en
FROM fact_shipping sh
LEFT JOIN dim_vendor v ON v.vendor_id = sh.vendor_id
LEFT JOIN dim_branch b ON b.branch_code = sh.origin_branch_code;
