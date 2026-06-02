# -*- coding: utf-8 -*-
"""Deterministic guardrails: an input tagger (regex) + an output validator/repairer.

    from fahmai.agents.guardrails import scan_input, check_output, scrub, InputFlags
"""
from fahmai.agents.guardrails.input_guard import InputFlags, scan_input
from fahmai.agents.guardrails.output_guard import (
    Violation,
    check_output,
    force_decline,
    is_wellformed_refusal,
    scrub,
)

__all__ = ["scan_input", "InputFlags", "check_output", "scrub", "force_decline",
           "Violation", "is_wellformed_refusal"]
