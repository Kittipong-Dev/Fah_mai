"""Agent tools: sql_query, search_docs, get_document (+ schema_card context)."""
from fahmai.db import get_engine

# one shared engine for all tools (lazy pool)
ENGINE = get_engine()
