"""Supabase Postgres connection helper.

Builds a SQLAlchemy engine from .env. Connection precedence:
1. DATABASE_URL          -- explicit full string (e.g. Supabase session pooler), wins if set
2. SUPABASE_DB_HOST/...  -- host/port/user override (e.g. pooler host + user postgres.<ref>)
3. direct connection     -- db.<project-ref>.supabase.co:5432 (IPv6-only on free tier)

If the direct connection fails (common on IPv4-only networks), grab the
"Session pooler" connection string from the Supabase dashboard
(Project Settings -> Database -> Connection string) and put it in .env as DATABASE_URL.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def project_ref() -> str:
    return urlparse(os.environ["SUPABASE_URL"]).hostname.split(".")[0]


def database_url() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    pwd = quote(os.environ["SUPABASE_PASSWORD"], safe="")
    ref = project_ref()
    # Default to the Supabase session pooler: the direct db.<ref> host is IPv6-only and does not
    # resolve on most IPv4 networks. Callers no longer need to set SUPABASE_DB_* themselves.
    host = os.getenv("SUPABASE_DB_HOST", "aws-1-ap-southeast-1.pooler.supabase.com")
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    # the pooler requires user "postgres.<project-ref>"; a direct db.<ref> host uses plain "postgres"
    default_user = f"postgres.{ref}" if "pooler" in host else "postgres"
    user = os.getenv("SUPABASE_DB_USER", default_user)
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/postgres"


def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


if __name__ == "__main__":
    from sqlalchemy import text

    eng = get_engine()
    with eng.connect() as conn:
        v = conn.execute(text("select version()")).scalar()
        print("connected OK")
        print(v)
