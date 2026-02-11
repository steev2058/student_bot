from sqlalchemy.orm import Session
from app.models.entities import Chunk, Subject, TocItem
from app.rag.embeddings import deterministic_embedding
from app.services.cache_service import make_cache_key, get_cache, set_cache
from rapidfuzz import fuzz
from app.core.config import settings


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def retrieve_chunks(db: Session, subject_id: int, query: str, lesson_range: tuple[int | None, int | None] | None = None, top_k: int = 5):
    qv = deterministic_embedding(query)
    q = db.query(Chunk).filter(Chunk.subject_id == subject_id)
    if lesson_range:
        start, end = lesson_range
        if start is not None:
            q = q.filter(Chunk.pdf_page_index >= start)
        if end is not None:
            q = q.filter(Chunk.pdf_page_index <= end)
    rows = q.limit(1200).all()

    kw_sorted = sorted(rows, key=lambda r: fuzz.token_set_ratio(query, r.content[:300]), reverse=True)[:120]

    scored = []
    for r in kw_sorted:
        rv = deterministic_embedding(r.content[:500])
        scored.append((_cos(qv, rv), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def _build_citation(db: Session, subject: Subject | None, chunk: Chunk) -> str:
    toc = db.query(TocItem).filter(TocItem.id == chunk.toc_item_id).first() if chunk.toc_item_id else None
    unit = None
    if toc and toc.parent_id:
        unit = db.query(TocItem).filter(TocItem.id == toc.parent_id).first()

    subject_label = subject.name_ar if subject else "المادة"
    lesson_label = toc.title if toc else "درس غير محدد"
    if unit:
        lesson_label = f"{unit.title} / {lesson_label}"

    page_label = f"PDF p{chunk.pdf_page_index + 1}"
    if chunk.printed_page_number is not None:
        page_label = f"ص{chunk.printed_page_number} (PDF p{chunk.pdf_page_index + 1})"

    return f"{subject_label} | {lesson_label} | {page_label}"


def answer_question(db: Session, user_id: int, subject_id: int, question: str, lesson_range, watermark: str | None = None):
    subj = db.query(Subject).filter(Subject.id == subject_id).first()
    content_version = str(subj.content_version if subj else settings.CONTENT_VERSION)

    lrange = None
    if lesson_range and isinstance(lesson_range, list) and len(lesson_range) == 2:
        lrange = (lesson_range[0], lesson_range[1])

    ckey = make_cache_key("explain", str(subject_id), str(lrange), question, "det", content_version)
    cached = get_cache(db, ckey)
    if cached:
        return {"answer": cached, "cached": True}

    rkey = make_cache_key("retrieve", str(subject_id), str(lrange), question, "det", content_version)
    cached_retrieval = get_cache(db, rkey)
    if cached_retrieval:
        ids = [int(x) for x in cached_retrieval.split(",") if x]
        retrieved = db.query(Chunk).filter(Chunk.id.in_(ids)).all() if ids else []
    else:
        retrieved = retrieve_chunks(db, subject_id, question, lrange)
        set_cache(db, rkey, ",".join(str(c.id) for c in retrieved), ttl_days=7)

    if not retrieved:
        return {
            "answer": "لا أملك مراجع كافية من نطاق الدرس الحالي. من فضلك اختر درساً محدداً أو ضيّق السؤال أكثر.",
            "citations": [],
        }

    citations = [_build_citation(db, subj, c) for c in retrieved]
    if not citations:
        return {
            "answer": "لا يمكنني الإجابة دون توثيق واضح. من فضلك اختر درساً/وحدة ثم أعد السؤال.",
            "citations": [],
        }

    body = "\n".join([c.content[:180] for c in retrieved[:3]])
    answer = f"بناءً على محتوى الكتاب:\n{body}\n\nالمراجع:\n- " + "\n- ".join(citations)

    if "المراجع" not in answer:
        return {
            "answer": "لا يمكنني الإجابة دون توثيق من الكتاب. من فضلك أعد صياغة السؤال داخل نطاق الدرس.",
            "citations": [],
        }

    if watermark:
        answer = f"{answer}\n\n{watermark}"
    set_cache(db, ckey, answer, ttl_days=30)
    return {"answer": answer, "citations": citations, "cached": False}
