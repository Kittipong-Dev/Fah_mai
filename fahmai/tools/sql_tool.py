"""sql_query: read-only text-to-SQL execution over Supabase Postgres.

Safety: runs inside a READ ONLY transaction with a statement timeout, plus a keyword
pre-check. Results are truncated (rows + cell width) and returned as a markdown table
string for the agent. On error, returns "SQL ERROR: ..." so the agent can self-correct.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from fahmai.tools import SQL_ENGINE as ENGINE

# The real guard is `SET TRANSACTION READ ONLY` (Postgres rejects any write at execute).
# This regex is a secondary check, applied AFTER stripping string literals + comments so that
# common words inside ILIKE patterns (e.g. '%reset%', '%merge%') don't cause false positives.
# Kept to genuine DML/DDL (e.g. a data-modifying CTE: WITH x AS (DELETE ...) SELECT ...).
_LIT = re.compile(r"'(?:[^']|'')*'")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|merge|create)\b",
    re.IGNORECASE,
)


def _code_only(s: str) -> str:
    """Strip block/line comments and single-quoted literals so keyword checks see only SQL code."""
    s = _BLOCK_COMMENT.sub(" ", s)
    s = _LINE_COMMENT.sub(" ", s)
    return _LIT.sub("''", s)


def _clean_sql(s: str) -> str:
    """Strip a leading ```sql fence / bare 'sql' tag the LLM often prepends, so the query
    starts with the actual statement (leading -- comments are fine; Postgres ignores them)."""
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*[ \t]*\r?\n?", "", s)
        s = re.sub(r"\r?\n?```[ \t]*$", "", s).strip()
    s = re.sub(r"^(sql|postgresql|postgres)[ \t]*\r?\n", "", s, flags=re.IGNORECASE)
    return s.strip()


MAX_ROWS = 100
MAX_CELL = 300
TIMEOUT_MS = 30000


def _fmt(cols, rows, truncated_rows: bool) -> str:
    if not rows:
        return "(0 rows)"
    def cell(v):
        s = "" if v is None else str(v)
        return s if len(s) <= MAX_CELL else s[:MAX_CELL] + "…"
    head = " | ".join(cols)
    sep = " | ".join("---" for _ in cols)
    body = "\n".join(" | ".join(cell(v) for v in r) for r in rows)
    note = f"\n… ({len(rows)} rows shown; more exist — refine with LIMIT/aggregation)" if truncated_rows else f"\n({len(rows)} rows)"
    return f"{head}\n{sep}\n{body}{note}"


def sql_query(sql: str) -> str:
    """Execute a single read-only SELECT and return a markdown table (truncated)."""
    s = _clean_sql(sql).rstrip(";").strip()
    if not s:
        return "SQL ERROR: empty query"
    code = _code_only(s).strip().lower()   # comments/literals stripped -> first real token
    if not (code.startswith("select") or code.startswith("with")):
        return "SQL ERROR: only SELECT/WITH queries are allowed (read-only)."
    if _WRITE.search(_code_only(s)):
        return "SQL ERROR: write/DDL statement detected (read-only)."
    try:
        with ENGINE.connect() as c:
            with c.begin():
                c.execute(text("SET TRANSACTION READ ONLY"))
                c.execute(text(f"SET LOCAL statement_timeout = {TIMEOUT_MS}"))
                res = c.execute(text(s))
                cols = list(res.keys())
                rows = res.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        return _fmt(cols, rows[:MAX_ROWS], truncated)
    except Exception as e:  # noqa: BLE001
        return f"SQL ERROR: {str(e).splitlines()[0]}"


if __name__ == "__main__":
    # smoke checks against real questions
    print("EASY-001:", sql_query("select msrp_thb from dim_product where sku_id='NT-LT-001'"))
    print("\nEASY-013:", sql_query("select count(*) from dim_vendor"))
    print("\nFY2568 net:", sql_query("select round(sum(net_total_thb)) from v_sales where fiscal_year_ce=2025"))
    print("\nwrite blocked:", sql_query("update dim_vendor set name_en='x'"))
    print("\nHARD-018 count:", sql_query(
        "select count(*) from doc_corpus where channel='chat_works' and topic like 'E3%'"))
