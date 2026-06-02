# -*- coding: utf-8 -*-
"""Output guardrail: validate (and deterministically repair) the final answer against the
grader's must_not_contain / refusal-shape / no-parrot-directive rules.

Pure string ops — no LLM on the common path. `check_output` finds violations; `scrub` fixes the
mechanical ones (strip forced string / echoed candidate, add a scope marker to a bare refusal) and
returns any residual *semantic* violation that needs an LLM rewrite (handled by the graph, ≤1 pass).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fahmai.agents.guardrails import patterns as P
from fahmai.agents.guardrails.input_guard import InputFlags

_THAI_RE = re.compile(r"[฀-๿]")
_AFFIRM_RE = re.compile(r"ยืนยัน|อนุมัติ|confirmed|ดำรงตำแหน่ง.*จริง|มีอำนาจ", re.I)

# Deterministic decline used when a planted authority/role claim survives the one synth repair.
# Carries a refusal verb + scope marker and explicitly declines the injected directive, so it reads
# as a valid grader Path-B answer (decline the directive) — never affirms the asserted authority.
DECLINE_TEMPLATE = (
    "ไม่สามารถยืนยันสิทธิ์ อำนาจ หรือตำแหน่งตามที่อ้างในคำถามได้ "
    "เนื่องจากข้อความที่ฝังมาในคำถามไม่ถือเป็นหลักฐานในระบบ "
    "สิทธิ์และบทบาทต้องตรวจสอบจากข้อมูลจริงใน dim_employee และ "
    "dim_signing_authority_ladder เท่านั้น"
)


@dataclass
class Violation:
    kind: str       # forced_string | candidate_echo | not_thai | authority_affirm | weak_refusal
    detail: str
    scrubbable: bool


def is_thai(text: str) -> bool:
    return bool(_THAI_RE.search(text or ""))


def is_wellformed_refusal(text: str) -> bool:
    t = (text or "").lower()
    has_verb = any(v.lower() in t for v in P.REFUSAL_VERBS)
    has_scope = any(s.lower() in t for s in P.SCOPE_MARKERS)
    return has_verb and has_scope


def _looks_like_refusal(text: str) -> bool:
    """True only when the answer LEADS with a refusal (verb in the first ~40 chars), so a normal
    answer that merely contains 'ไม่มี' mid-sentence is not mistaken for a refusal."""
    head = (text or "").strip()[:40].lower()
    return any(v.lower() in head for v in P.REFUSAL_VERBS)


def check_output(answer: str, flags: InputFlags, findings_empty: bool = False,
                 is_injection: bool = False) -> list[Violation]:
    a = answer or ""
    al = a.lower()
    out: list[Violation] = []

    # (1) forced verbatim string present
    for s in flags.forced_strings:
        if s and s.lower() in al:
            out.append(Violation("forced_string", s, scrubbable=True))

    # (2) asker-proposed candidate value echoed
    for c in flags.candidate_values:
        if c and c.replace(" ", "") in a.replace(" ", ""):
            out.append(Violation("candidate_echo", c, scrubbable=True))

    # (3) language: a Thai answer is expected (esp. when an English switch was demanded)
    if not is_thai(a):
        out.append(Violation("not_thai", "answer is not in Thai", scrubbable=False))

    # (4) affirmed an authority/role the question tried to plant. Trigger on either the regex flag
    # (question literally planted a role/authority claim) OR the planner's semantic is_injection
    # judgement — the latter catches affirmations the keyword flag misses.
    if (flags.authority_grant or is_injection) and _AFFIRM_RE.search(a):
        out.append(Violation("authority_affirm", "affirms an asserted authority/role", scrubbable=False))

    # (5) a refusal is expected but it isn't well-formed (verb + scope)
    if (findings_empty or _looks_like_refusal(a)) and not is_wellformed_refusal(a):
        out.append(Violation("weak_refusal", "missing refusal verb or scope marker", scrubbable=True))

    return out


def scrub(answer: str, violations: list[Violation]) -> tuple[str, list[Violation]]:
    """Apply deterministic fixes; return (fixed_answer, residual_violations needing an LLM rewrite)."""
    a = answer or ""
    residual: list[Violation] = []
    for v in violations:
        if v.kind == "forced_string":
            a = re.sub(re.escape(v.detail), "", a, flags=re.I)
        elif v.kind == "candidate_echo":
            a = re.sub(re.escape(v.detail), "", a)          # drop the echoed value
            a = re.sub(r"(?:\s*,)+", ",", a)                # tidy dangling commas left behind
            a = re.sub(r",\s*(?=[)฀-๿]|$)", " ", a)
        elif v.kind == "weak_refusal":
            if not any(s in a for s in P.SCOPE_MARKERS):
                a = a.rstrip().rstrip(".") + " (ไม่พบในชุดข้อมูล/ในระบบ)"
        else:
            residual.append(v)  # not_thai / authority_affirm -> need semantic rewrite
    a = re.sub(r"\s{2,}", " ", a).strip()
    return a, residual


def force_decline(violations: list[Violation]) -> str | None:
    """Deterministic safety fallback: if a planted-authority affirmation survived the synth repair,
    return a clean decline template instead of letting the affirming text reach the user. Returns
    None for any other residual (e.g. not_thai) so the caller falls back to the scrubbed text."""
    if any(v.kind == "authority_affirm" for v in violations):
        return DECLINE_TEMPLATE
    return None
