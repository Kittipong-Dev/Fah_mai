"""Apply a .sql file to Supabase Postgres (statement-by-statement, $$-aware).

Usage: uv run python scripts/apply_sql.py scripts/setup_keys.sql
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fahmai.db import get_engine  # noqa: E402


def split_statements(sql: str) -> list[str]:
    """Split on ';' but ignore ';' inside -- line comments, /* */ blocks, '' strings, $$ blocks."""
    out, cur, i, n = [], [], 0, len(sql)
    in_line = in_block = in_dollar = in_squote = False
    while i < n:
        ch, two = sql[i], sql[i : i + 2]
        if in_line:
            cur.append(ch)
            if ch == "\n":
                in_line = False
            i += 1
        elif in_block:
            cur.append(ch)
            if two == "*/":
                cur.append(sql[i + 1]); i += 2; in_block = False
            else:
                i += 1
        elif in_dollar:
            if two == "$$":
                cur.append("$$"); i += 2; in_dollar = False
            else:
                cur.append(ch); i += 1
        elif in_squote:
            cur.append(ch)
            if ch == "'":
                in_squote = False
            i += 1
        elif two == "--":
            in_line = True; cur.append(two); i += 2
        elif two == "/*":
            in_block = True; cur.append(two); i += 2
        elif two == "$$":
            in_dollar = True; cur.append(two); i += 2
        elif ch == "'":
            in_squote = True; cur.append(ch); i += 1
        elif ch == ";":
            out.append("".join(cur)); cur = []; i += 1
        else:
            cur.append(ch); i += 1
    out.append("".join(cur))

    def clean(stmt: str) -> str:
        lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
        return "\n".join(lines).strip()

    return [c for c in (clean(s) for s in out) if c]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: apply_sql.py <file.sql>", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    stmts = split_statements(path.read_text(encoding="utf-8"))
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        pg = raw.driver_connection
        for n, stmt in enumerate(stmts, 1):
            head = " ".join(stmt.split())[:70]
            try:
                with pg.cursor() as cur:
                    cur.execute(stmt)
                print(f"  [{n:>2}/{len(stmts)}] OK  {head}")
            except Exception as e:  # noqa: BLE001
                pg.rollback()
                print(f"  [{n:>2}/{len(stmts)}] ERR {head}\n        -> {str(e).splitlines()[0]}")
                raise
        pg.commit()
    finally:
        raw.close()
    print(f"\napplied {len(stmts)} statements from {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
