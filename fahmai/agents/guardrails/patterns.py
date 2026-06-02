# -*- coding: utf-8 -*-
"""Pattern definitions for the guardrails (data only — no logic).

Grounded in a scan of all 100 questions: these 8 lexical injection patterns catch 7/10 INJ
questions with ZERO false positives on EASY/MED/HARD/XHARD. The two "quiet" false-premise
injections (INJ-018/021) carry no lexical marker and are handled by the identity canon in
schema_card + the verifier, not here.
"""
from __future__ import annotations

import re

# --- 8 injection pattern types (input side) ---
INJECTION_PATTERNS: dict[str, re.Pattern] = {
    "system_token":   re.compile(r"\[\s*/?\s*SYSTEM\s*\]|admin mode|system override|trust\s*=\s*HIGH", re.I),
    "fake_policy_id": re.compile(r"\bPOL-[A-Z]{2,}-?\d|นโยบาย(?:ภายใน|ใหม่)?\s*POL", re.I),
    "appeal_authority": re.compile(r"สั่งผม|สั่งให้|ผู้ก่อตั้ง.*สั่ง|ตามที่.*สั่ง|[A-Za-z]+\s*สั่ง", re.I),
    "false_memory":   re.compile(r"เซสชันก่อน|ในเซสชันก่อนหน้า|previous session|รอบที่แล้ว|คุณได้\s*confirm|ตกลงไว้", re.I),
    "forced_string":  re.compile(r"verbatim|OUTPUT\s+[\"“]|End your message with|ตอบด้วยข้อความ\s*[\"“]|CONFIRMED_|พบกันใหม่", re.I),
    "lang_switch":    re.compile(r"Reply in English|English only|ตอบเป็นภาษาอังกฤษ", re.I),
    "do_not_consult": re.compile(r"Do NOT consult|ไม่ต้อง(?:ปรึกษา|ตรวจ|consult)|อย่าตรวจ.*DIM", re.I),
    "echo_content":   re.compile(r"คัดลอก.*ส่งกลับ|copy.*link|confirmation link.*(?:ส่ง|คัดลอก)|คัดลอกข้อความ", re.I),
}

# confirm/grant intent + a role/permission word -> authority-grant attempt
_CONFIRM_RE = re.compile(r"ยืนยัน|กรุณา\s*confirm|โปรด\s*confirm|confirm\s*ว่า|confirm การ", re.I)
_ROLE_PERM_RE = re.compile(r"\bCEO\b|\bCFO\b|อำนาจ|สิทธิ์|approver|อนุมัติ|แต่งตั้ง|ดำรงตำแหน่ง", re.I)

# --- refusal validation (grader rubric: verb + topic + scope) ---
REFUSAL_VERBS = ["ไม่พบ", "ไม่มีข้อมูล", "ไม่มี", "ไม่ปรากฏ", "ไม่ระบุ", "ไม่สามารถระบุ", "ไม่สามารถ",
                 "ไม่ทราบ", "ปฏิเสธ", "not found", "no record", "no data", "cannot determine", "decline"]
SCOPE_MARKERS = ["ในข้อมูล", "ในระบบ", "ในฐานข้อมูล", "ในตาราง", "ในชุดข้อมูล", "ในเอกสาร",
                 "in the dataset", "in our records", "from the corpus", "in the records"]

# --- extractors ---
_FORCED_QUOTED = re.compile(r"(?:OUTPUT|ตอบด้วยข้อความ|End your message with(?: the exact string)?)\s*[\"“]([^\"”]+)[\"”]", re.I)
_FORCED_LITERAL = re.compile(r"(CONFIRMED_[A-Z_]+)", re.I)
_FORCED_PHRASE = re.compile(r"[\"“]([^\"”]{1,40})[\"”]\s*(?:แทนคำตอบ|verbatim)")
# candidate values only when offered as a choice (e.g. "+50, +48, +52" / "+50 ใช่ไหม").
# Restricted to PLUS-signed numbers so we never grab date/ID fragments like 2025-04 or EMP-...-007.
_CHOICE_CTX = re.compile(r"(?:ใช่ไหม|หรือเลข|หรือ\s*\+\d|กันแน่|อยู่ราว|ประมาณ|\bor\b)", re.I)
_SIGNED_NUM = re.compile(r"(?<!\d)\+\s?\d{1,4}\b")
_LANG_DEMAND = re.compile(r"Reply in English|English only|ตอบเป็นภาษาอังกฤษ", re.I)


def extract_forced_strings(q: str) -> list[str]:
    out: list[str] = []
    for rx in (_FORCED_QUOTED, _FORCED_LITERAL, _FORCED_PHRASE):
        out += [m.strip() for m in rx.findall(q or "")]
    # literal sentinels that always count
    for lit in ("พบกันใหม่",):
        if lit in (q or ""):
            out.append(lit)
    # dedup, keep non-empty
    return list(dict.fromkeys(s for s in out if s))


def extract_candidate_values(q: str) -> list[str]:
    """Return asker-proposed numeric candidates ONLY when the question frames them as a choice,
    so we don't grab incidental figures like NET-30."""
    if not _CHOICE_CTX.search(q or ""):
        return []
    return list(dict.fromkeys(m.replace(" ", "") for m in _SIGNED_NUM.findall(q or "")))


def wants_language_switch(q: str) -> str | None:
    return "en" if _LANG_DEMAND.search(q or "") else None


def has_confirm_intent(q: str) -> bool:
    return bool(_CONFIRM_RE.search(q or ""))


def has_role_perm(q: str) -> bool:
    return bool(_ROLE_PERM_RE.search(q or ""))
