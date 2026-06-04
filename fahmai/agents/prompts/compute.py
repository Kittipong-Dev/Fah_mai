# -*- coding: utf-8 -*-
"""Compute node prompt (PAL pattern) — extract derived-metric formulas from findings.

The LLM does NOT do the arithmetic; it only names the operands and the expression. A
deterministic Python evaluator (fahmai.utils.safe_eval) computes the result. This removes
LLM arithmetic errors on ratios / baselines / percentages / multi-step derivations.
"""

COMPUTE_SYS = (
    "You are the compute step of the FahMai data team. Look at the QUESTION and the FINDINGS. "
    "Identify EVERY derived numeric metric the question asks for that must be computed by "
    "ARITHMETIC over numbers already present in the findings (e.g. a ratio, percentage, baseline "
    "average, sum of parts, multiplier, foregone revenue, ROI, lift).\n"
    "For each, extract:\n"
    "  name       — short label of the metric (in the question's terms)\n"
    "  expression — an arithmetic expression using ONLY operand names, numbers, + - * / % ** ( ), "
    "and the functions round/abs/min/max/sum/len\n"
    "  operands   — a map of operand_name -> numeric_value, taking the EXACT numbers from the "
    "findings (strip commas/units; use raw numbers)\n"
    "RULES:\n"
    "- Only emit a computation when ALL operands are present as concrete numbers in the findings. "
    "If a needed number is missing, SKIP that metric (do not guess).\n"
    "- Do NOT restate numbers that are already directly given in a finding — only NEW derived values.\n"
    "- Operand values must be plain numbers (e.g. 1500000, not '1,500,000 บาท').\n"
    "- If the question needs no derived arithmetic, return an empty list.\n"
    'Respond ONLY with JSON: {"computations":[{"name":"...","expression":"...",'
    '"operands":{"a":1,"b":2}}]}'
)
