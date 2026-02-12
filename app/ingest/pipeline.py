from pathlib import Path
import fitz
from sqlalchemy.orm import Session
from app.core.config import settings
from app.ingest.toc_extractor import extract_toc_with_fallback
from app.ingest.pdf_text_utils import extract_page_text_layout_aware, normalize_arabic, chunk_text_words
from app.models.entities import Subject, TocItem, Chunk, LessonEmbedding
from app.rag.embeddings import deterministic_embedding


def _build_synthetic_toc(page_count: int) -> list[dict]:
    if page_count <= 0:
        return []
    lesson_span = 12
    unit_size = 4
    items: list[dict] = []
    lesson_idx = 0
    unit_idx = 0
    for start in range(0, page_count, lesson_span):
        if lesson_idx % unit_size == 0:
            unit_idx += 1
            items.append({"title": f"الوحدة {unit_idx}", "level": 1, "page": start})
        lesson_idx += 1
        items.append({"title": f"الدرس {lesson_idx}", "level": 2, "page": start})
    return items


def _resolve_source_pdf_path(pdf_path: str) -> str:
    if not settings.PDF_USE_OCR:
        return pdf_path
    ocr_candidate = Path(settings.PDF_OCR_DIR) / Path(pdf_path).name
    if ocr_candidate.exists():
        return str(ocr_candidate)
    return pdf_path


def _resolve_start_page(item: dict, mapping: dict[int, int]) -> int | None:
    page = item.get("page")
    if page is not None:
        return int(page)
    pp = item.get("printed_page")
    if pp is not None and int(pp) in mapping:
        return int(mapping[int(pp)])
    return None


def ingest_subject(db: Session, subject_code: str, name_ar: str, pdf_path: str, content_version: int):
    source_pdf_path = _resolve_source_pdf_path(pdf_path)

    subj = db.query(Subject).filter(Subject.code == subject_code).first()
    if not subj:
        subj = Subject(code=subject_code, name_ar=name_ar, pdf_path=source_pdf_path, content_version=content_version)
        db.add(subj)
        db.commit()
        db.refresh(subj)
    else:
        subj.content_version = content_version
        db.commit()

    toc_debug = extract_toc_with_fallback(source_pdf_path, subject_code)

    db.query(TocItem).filter(TocItem.subject_id == subj.id).delete()
    db.query(Chunk).filter(Chunk.subject_id == subj.id).delete()
    db.query(LessonEmbedding).filter(LessonEmbedding.subject_id == subj.id).delete()
    db.commit()

    toc_items: list[TocItem] = []
    stack: list[TocItem] = []
    mapping = {int(k): int(v) for k, v in (toc_debug.get("page_mapping") or {}).items()}
    raw_items = toc_debug.get("items") or []

    # Hard fallback: if TOC extraction returns nothing, synthesize a navigable plan.
    if not raw_items:
        doc_tmp = fitz.open(source_pdf_path)
        raw_items = _build_synthetic_toc(doc_tmp.page_count)
        doc_tmp.close()

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

    doc = fitz.open(source_pdf_path)
    lesson_items = [x for x in toc_items if x.level >= 2 and x.start_pdf_page is not None]
    lesson_items.sort(key=lambda x: x.start_pdf_page)
    reverse_mapping = {int(pdf_idx): int(printed) for printed, pdf_idx in mapping.items()}

    for i in range(doc.page_count):
        raw_text = extract_page_text_layout_aware(doc[i])
        normalized_text = normalize_arabic(raw_text)
        chunks = chunk_text_words(normalized_text, min_words=300, max_words=700, overlap_words=90)
        toc_id = None
        for ls in lesson_items:
            end = ls.end_pdf_page if ls.end_pdf_page is not None else doc.page_count - 1
            if (ls.start_pdf_page or 0) <= i <= end:
                toc_id = ls.id
                break
        printed_page_number = reverse_mapping.get(i)
        for c in chunks:
            db.add(Chunk(subject_id=subj.id, toc_item_id=toc_id, pdf_page_index=i, printed_page_number=printed_page_number, content=c))
    db.commit()

    for ti in lesson_items:
        texts = db.query(Chunk).filter(Chunk.subject_id == subj.id, Chunk.toc_item_id == ti.id).limit(15).all()
        summary = "\n".join([t.content[:200] for t in texts])[:2000] or ""
        emb = deterministic_embedding(summary or f"lesson-{ti.id}")
        db.add(LessonEmbedding(subject_id=subj.id, toc_item_id=ti.id, summary=summary, embedding=emb))
    db.commit()

    return {"subject": subject_code, "toc_items": len(toc_items)}
