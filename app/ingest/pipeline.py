from pathlib import Path
import fitz
from sqlalchemy.orm import Session
from app.ingest.toc_extractor import extract_toc_with_fallback
from app.models.entities import Subject, TocItem, Chunk, LessonEmbedding
from app.rag.embeddings import deterministic_embedding


def _chunk_text(text: str, max_len: int = 900):
    words = text.split()
    cur, out = [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) > max_len:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def _resolve_start_page(item: dict, mapping: dict[int, int]) -> int | None:
    page = item.get("page")
    if page is not None:
        return int(page)
    pp = item.get("printed_page")
    if pp is not None and int(pp) in mapping:
        return int(mapping[int(pp)])
    return None


def ingest_subject(db: Session, subject_code: str, name_ar: str, pdf_path: str, content_version: int):
    subj = db.query(Subject).filter(Subject.code == subject_code).first()
    if not subj:
        subj = Subject(code=subject_code, name_ar=name_ar, pdf_path=pdf_path, content_version=content_version)
        db.add(subj)
        db.commit()
        db.refresh(subj)
    else:
        subj.content_version = content_version
        db.commit()

    toc_debug = extract_toc_with_fallback(pdf_path, subject_code)

    db.query(TocItem).filter(TocItem.subject_id == subj.id).delete()
    db.query(Chunk).filter(Chunk.subject_id == subj.id).delete()
    db.query(LessonEmbedding).filter(LessonEmbedding.subject_id == subj.id).delete()
    db.commit()

    toc_items: list[TocItem] = []
    stack: list[TocItem] = []
    mapping = {int(k): int(v) for k, v in (toc_debug.get("page_mapping") or {}).items()}
    raw_items = toc_debug.get("items") or []

    for i, it in enumerate(raw_items):
        level = int(it.get("level", 2) or 2)
        while len(stack) >= level:
            stack.pop()
        parent = stack[-1] if stack else None

        ti = TocItem(
            subject_id=subj.id,
            parent_id=parent.id if parent else None,
            title=it.get("title", f"Item {i+1}"),
            level=level,
            order_index=i,
            start_pdf_page=_resolve_start_page(it, mapping),
            printed_page_start=it.get("printed_page"),
        )
        db.add(ti)
        db.flush()
        toc_items.append(ti)
        stack.append(ti)

    # Fill end pages using next start page.
    for idx, ti in enumerate(toc_items):
        if ti.start_pdf_page is None:
            continue
        nxt = None
        for j in range(idx + 1, len(toc_items)):
            if toc_items[j].start_pdf_page is not None and toc_items[j].start_pdf_page > ti.start_pdf_page:
                nxt = toc_items[j].start_pdf_page
                break
        ti.end_pdf_page = (nxt - 1) if nxt is not None else None
    db.commit()

    doc = fitz.open(pdf_path)
    lesson_items = [x for x in toc_items if x.level >= 2 and x.start_pdf_page is not None]
    lesson_items.sort(key=lambda x: x.start_pdf_page)

    for i in range(doc.page_count):
        txt = doc[i].get_text("text")
        chunks = _chunk_text(txt)
        toc_id = None
        for ls in lesson_items:
            end = ls.end_pdf_page if ls.end_pdf_page is not None else doc.page_count - 1
            if (ls.start_pdf_page or 0) <= i <= end:
                toc_id = ls.id
                break
        for c in chunks:
            db.add(Chunk(subject_id=subj.id, toc_item_id=toc_id, pdf_page_index=i, printed_page_number=None, content=c))
    db.commit()

    for ti in lesson_items:
        texts = db.query(Chunk).filter(Chunk.subject_id == subj.id, Chunk.toc_item_id == ti.id).limit(15).all()
        summary = "\n".join([t.content[:200] for t in texts])[:2000] or ""
        emb = deterministic_embedding(summary or f"lesson-{ti.id}")
        db.add(LessonEmbedding(subject_id=subj.id, toc_item_id=ti.id, summary=summary, embedding=emb))
    db.commit()

    return {"subject": subject_code, "toc_items": len(toc_items)}
