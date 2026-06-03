"""Agent tools: sql_query, search_docs, get_document (+ schema_card context)."""
from fahmai.db import get_engine, get_sql_engine

# ENGINE     = Supabase warehouse (doc tools: doc_corpus / doc_vec)
# SQL_ENGINE = grading DB for the sql_query tool (fah_sai_lpk_* schemas); Supabase if unset
ENGINE = get_engine()
SQL_ENGINE = get_sql_engine()
