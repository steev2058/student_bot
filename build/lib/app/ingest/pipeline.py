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

    toc_item_ids = []
    for i, it in enumerate(toc_debug["items"]):
        ti = TocItem(
            subject_id=subj.id,
            title=it.get("title", f"Item {i+1}"),
            level=it.get("level", 1),
            order_index=i,
            start_pdf_page=it.get("page"),
            printed_page_start=it.get("printed_page"),
        )
        db.add(ti)
        db.flush()
        toc_item_ids.append(ti.id)
    db.commit()

    doc = fitz.open(pdf_path)
    for i in range(doc.page_count):
        txt = doc[i].get_text("text")
        chunks = _chunk_text(txt)
        toc_id = toc_item_ids[min(i, len(toc_item_ids)-1)] if toc_item_ids else None
        for c in chunks:
            db.add(Chunk(subject_id=subj.id, toc_item_id=toc_id, pdf_page_index=i, printed_page_number=None, content=c))
    db.commit()

    for ti_id in toc_item_ids:
        texts = db.query(Chunk).filter(Chunk.subject_id == subj.id, Chunk.toc_item_id == ti_id).limit(15).all()
        summary = "\n".join([t.content[:200] for t in texts])[:2000] or ""
        emb = deterministic_embedding(summary or f"lesson-{ti_id}")
        db.add(LessonEmbedding(subject_id=subj.id, toc_item_id=ti_id, summary=summary, embedding=emb))
    db.commit()

    return {"subject": subject_code, "toc_items": len(toc_item_ids)}
