from sqlalchemy.orm import Session
from app.models.entities import Chunk, Subject
from app.rag.embeddings import deterministic_embedding
from app.services.cache_service import make_cache_key, get_cache, set_cache
from rapidfuzz import fuzz
from app.core.config import settings


def _cos(a, b):
    return sum(x*y for x,y in zip(a,b))


def retrieve_chunks(db: Session, subject_id: int, query: str, lesson_range: tuple[int, int] | None = None, top_k: int = 5):
    qv = deterministic_embedding(query)
    q = db.query(Chunk).filter(Chunk.subject_id == subject_id)
    if lesson_range:
        q = q.filter(Chunk.toc_item_id >= lesson_range[0], Chunk.toc_item_id <= lesson_range[1])
    rows = q.limit(1200).all()

    # Stage 1: keyword ranking
    kw_sorted = sorted(rows, key=lambda r: fuzz.token_set_ratio(query, r.content[:300]), reverse=True)[:120]

    # Stage 2: semantic rerank
    scored = []
    for r in kw_sorted:
        rv = deterministic_embedding(r.content[:500])
        scored.append((_cos(qv, rv), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def answer_question(db: Session, user_id: int, subject_id: int, question: str, lesson_range, watermark: str | None = None):
    subj = db.query(Subject).filter(Subject.id == subject_id).first()
    content_version = str(subj.content_version if subj else settings.CONTENT_VERSION)
    lrange = tuple(lesson_range) if lesson_range and isinstance(lesson_range, list) else None
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
        return {"answer": "لا أملك أدلة كافية من الدرس المحدد. رجاءً حدّد درساً/صفحات أدق.", "citations": []}

    citations = [f"ص.{c.pdf_page_index+1}" for c in retrieved]
    body = "\n".join([c.content[:180] for c in retrieved[:3]])
    answer = f"بناءً على محتوى الدرس:\n{body}\n\nالمراجع: {', '.join(citations)}"

    if "المراجع:" not in answer:
        return {"answer": "لا يمكنني الإجابة دون توثيق من الكتاب. من فضلك أعد صياغة السؤال داخل نطاق الدرس."}

    if watermark:
        answer = f"{answer}\n\n{watermark}"
    set_cache(db, ckey, answer, ttl_days=30)
    return {"answer": answer, "citations": citations, "cached": False}
