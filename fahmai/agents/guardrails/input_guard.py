# -*- coding: utf-8 -*-
"""Input guardrail: tag a question with injection signals (pure regex, no LLM, ~microseconds).

This NEVER blocks — it only annotates, so a benign-but-injection-shaped question (e.g. INJ-005)
is still answered. The flags feed the synthesizer (so it knows which string/values to avoid) and
the output guardrail (so it can verify the final answer deterministically).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fahmai.agents.guardrails import patterns as P


@dataclass
class InputFlags:
    is_injection: bool = False
    directives: list[str] = field(default_factory=list)     # which INJECTION_PATTERNS fired
    forced_strings: list[str] = field(default_factory=list)  # verbatim strings the answer must NOT contain
    candidate_values: list[str] = field(default_factory=list)  # asker-proposed values not to echo
    lang_demand: str | None = None                           # e.g. "en" when an English-only switch is demanded
    authority_grant: bool = False                            # tries to get a role/permission confirmed

    def as_dict(self) -> dict:
        return {
            "is_injection": self.is_injection,
            "directives": self.directives,
            "forced_strings": self.forced_strings,
            "candidate_values": self.candidate_values,
            "lang_demand": self.lang_demand,
            "authority_grant": self.authority_grant,
        }


def scan_input(question: str) -> InputFlags:
    q = question or ""
    directives = [name for name, rx in P.INJECTION_PATTERNS.items() if rx.search(q)]
    forced = P.extract_forced_strings(q)
    candidates = P.extract_candidate_values(q)
    lang = P.wants_language_switch(q)
    authority_grant = P.has_confirm_intent(q) and P.has_role_perm(q) and bool(
        {"appeal_authority", "false_memory", "system_token", "fake_policy_id"} & set(directives)
    )
    is_injection = bool(directives) or authority_grant
    return InputFlags(
        is_injection=is_injection,
        directives=directives,
        forced_strings=forced,
        candidate_values=candidates,
        lang_demand=lang,
        authority_grant=authority_grant,
    )
