from sqlalchemy.orm import Session
from app.models.entities import Chunk, Subject, TocItem
from app.rag.embeddings import deterministic_embedding
from app.services.cache_service import make_cache_key, get_cache, set_cache
from rapidfuzz import fuzz
from app.core.config import settings
import re


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

    stop_terms = {"ما", "ماذا", "هل", "على", "الى", "إلى", "في", "من", "عن", "احسب", "اكتب", "عرّف", "عرف", "the", "what", "is"}
    q_terms = [t for t in re.findall(r"[\w\u0600-\u06FF]+", query.lower()) if len(t) >= 3 and t not in stop_terms]

    ranked = []
    for r in rows:
        txt = (r.content or "").lower()
        kw_score = fuzz.token_set_ratio(query, r.content[:300])
        overlap = sum(1 for t in q_terms if t in txt)
        rv = deterministic_embedding(r.content[:500])
        sem_score = _cos(qv, rv)
        ranked.append((kw_score, overlap, sem_score, r))

    # Hard guard against off-topic / out-of-book hallucinations:
    # require lexical overlap on meaningful terms from the question.
    filtered = [x for x in ranked if x[1] >= 1 and x[0] >= 20]
    if not filtered:
        return []

    filtered.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
    return [r for _, _, _, r in filtered[:top_k]]


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


def _extract_useful_lines(text: str, query: str, limit: int = 4) -> list[str]:
    q_terms = [t for t in re.findall(r"[\w\u0600-\u06FF]+", query.lower()) if len(t) >= 3]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    good = []
    for ln in lines:
        # skip noisy numeric/table-only lines
        if re.fullmatch(r"[\d\s\-–—.,:;()]+", ln):
            continue
        if len(ln) < 20:
            continue
        ln_low = ln.lower()
        score = sum(1 for t in q_terms if t in ln_low)
        if score > 0:
            good.append((score, ln))
    good.sort(key=lambda x: x[0], reverse=True)
    out = [ln for _, ln in good[:limit]]
    if out:
        return out

    # fallback: first non-noisy lines
    for ln in lines:
        if len(ln) >= 20 and not re.fullmatch(r"[\d\s\-–—.,:;()]+", ln):
            out.append(ln)
        if len(out) >= limit:
            break
    return out


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

    extracted: list[str] = []
    for c in retrieved[:4]:
        extracted.extend(_extract_useful_lines(c.content, question, limit=2))
    # deduplicate while preserving order
    seen = set()
    filtered = []
    for ln in extracted:
        key = ln.strip()
        if key and key not in seen:
            seen.add(key)
            filtered.append(key)
    body = "\n".join(filtered[:5])
    if not body:
        return {
            "answer": "لم أجد نصًا واضحًا قابلًا للتوثيق في نطاق الدرس الحالي. اختر درسًا أدق أو أعد صياغة السؤال.",
            "citations": citations,
        }

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
