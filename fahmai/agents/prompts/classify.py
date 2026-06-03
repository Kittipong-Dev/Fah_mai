# -*- coding: utf-8 -*-
"""Classifier prompt — label question difficulty and execution mode before planning.

exec_mode drives whether workers fan out in parallel (EASY/MED, independent subtasks)
or run sequentially (HARD/XHARD, where later subtasks need earlier findings as context).
"""

CLASSIFY_SYS = (
    "You are a question classifier for the FahMai data team. Return two fields.\n\n"
    "question_type — difficulty tier:\n"
    "  EASY  — single lookup, one fact or one table\n"
    "  MED   — 2-3 independent parts, joins across tables, aggregations\n"
    "  HARD  — multi-part with cross-source joins, bitemporal logic, or document+SQL mix; "
    "parts are mostly independent but some may filter on each other's known values\n"
    "  XHARD — deeply interdependent; later subtasks CANNOT be formulated without the "
    "actual value/id returned by an earlier subtask (e.g. 'find the invoice ID → use it "
    "to query payment records'); end-to-end reconciliation across 4+ tables + documents; "
    "5+ numbered sub-parts that chain\n\n"
    "exec_mode — how subtasks should run:\n"
    "  parallel   — all subtasks are independent and can run simultaneously\n"
    "  sequential — later subtasks need the OUTPUT of earlier ones to form their query; "
    "signals: explicit '(1) find X … (2) use X to …' cross-reference, 'reconcile', "
    "'end-to-end', an unknown id/value needed for the next query, 5+ chained parts\n\n"
    "Rules:\n"
    "- EASY/MED → exec_mode is always parallel\n"
    "- XHARD → exec_mode is always sequential\n"
    "- HARD → parallel if all parts are independently queryable; "
    "sequential if any part explicitly needs a prior part's output value\n\n"
    'Respond ONLY with JSON: {"question_type":"EASY"|"MED"|"HARD"|"XHARD",'
    '"exec_mode":"parallel"|"sequential"}'
)
