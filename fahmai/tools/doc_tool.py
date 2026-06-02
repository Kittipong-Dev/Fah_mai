"""search_docs (hybrid: metadata filter + optional keyword + vector rank) and get_document.

search_docs: semantic retrieval over doc_corpus⋈doc_vec, pre-filtered by metadata
(channel/topic/date) and optionally by an exact keyword (ILIKE) — exactly the access
pattern the questions need. get_document: full text of one doc for phrase/amount extraction.
"""
from __future__ import annotations

from sqlalchemy import text

from fahmai.embed import embed_batch
from fahmai.tools import ENGINE

SNIPPET = 280
DOC_MAXCHARS = 12000


def _vec(query: str) -> str:
    return "[" + ",".join(f"{x:.5f}" for x in embed_batch([query])[0]) + "]"


def search_docs(query: str, channel: str | None = None, topic: str | None = None,
                date_from: str | None = None, date_to: str | None = None,
                keyword: str | None = None, k: int = 8) -> str:
    """Hybrid doc search. Filters: channel, topic (prefix match), date range, exact keyword (ILIKE)."""
    where, params = [], {"q": _vec(query), "k": int(k)}
    if channel:
        where.append("dc.channel = :channel"); params["channel"] = channel
    if topic:
        where.append("dc.topic ILIKE :topic"); params["topic"] = f"{topic}%"
    if date_from:
        where.append("dc.doc_date >= :df"); params["df"] = date_from
    if date_to:
        where.append("dc.doc_date <= :dt"); params["dt"] = date_to
    if keyword:
        where.append("dc.content ILIKE :kw"); params["kw"] = f"%{keyword}%"
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        select dc.doc_id, dc.channel, dc.doc_date, dc.topic,
               round((1 - (dv.embedding <=> cast(:q as halfvec)))::numeric, 3) sim,
               left(dc.content, {SNIPPET}) snippet
        from doc_corpus dc join doc_vec dv using (doc_id)
        {clause}
        order by dv.embedding <=> cast(:q as halfvec)
        limit :k
    """
    try:
        with ENGINE.connect() as c:
            rows = c.execute(text(sql), params).fetchall()
    except Exception as e:  # noqa: BLE001
        return f"SEARCH ERROR: {str(e).splitlines()[0]}"
    if not rows:
        return "(no matching documents)"
    out = []
    for r in rows:
        snip = " ".join((r.snippet or "").split())
        out.append(f"[{r.sim}] {r.doc_id} ({r.channel}, {r.doc_date}, topic={r.topic or '-'})\n    {snip}")
    return "\n".join(out)


def get_document(doc_id: str) -> str:
    """Return full content + metadata for one doc_id (for phrase/amount extraction)."""
    with ENGINE.connect() as c:
        r = c.execute(text("""select doc_id, channel, doc_date, topic, participants, path, content
                              from doc_corpus where doc_id = :id"""), {"id": doc_id}).fetchone()
    if not r:
        return f"(no document with doc_id={doc_id})"
    content = r.content or ""
    if len(content) > DOC_MAXCHARS:
        content = content[:DOC_MAXCHARS] + "\n…(truncated)"
    meta = f"doc_id={r.doc_id} channel={r.channel} date={r.doc_date} topic={r.topic or '-'}"
    if r.participants:
        meta += f" participants={r.participants}"
    return f"{meta}\npath={r.path}\n---\n{content}"


if __name__ == "__main__":
    print("=== search FAQ (mini pc) ===")
    print(search_docs("จอใช้กับ Mini PC ดาวเหนือได้ไหม", channel="kb_product", k=3))
    print("\n=== search chat_works invoice (DQ3) ===")
    print(search_docs("invoice PayWise ออกเลขซ้ำ", channel="chat_works", date_from="2025-04-05",
                      date_to="2025-04-05", k=3))
    print("\n=== get_document MEMO-PM1 ===")
    print(get_document("MEMO-PM1-2025-02-15")[:600])
