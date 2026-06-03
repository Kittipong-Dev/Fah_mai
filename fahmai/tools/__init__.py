"""Agent tools: sql_query, search_docs, get_document (+ schema_card context)."""
from fahmai.db import get_engine

# one shared engine for all tools (lazy pool). Missing env is tolerated at import time so tests and
# schema-only helpers can load without a live database configuration.
try:
    ENGINE = get_engine()
except Exception:  # noqa: BLE001
    ENGINE = None
