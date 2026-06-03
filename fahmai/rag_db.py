# -*- coding: utf-8 -*-
"""SQLAlchemy engine for the pgvector RAG database (rag_chunks table).

Separate from fahmai/db.py (Supabase warehouse). Set RAG_DATABASE_URL in .env.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def get_rag_engine() -> Engine:
    url = os.environ["RAG_DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2)


RAG_ENGINE = get_rag_engine()
