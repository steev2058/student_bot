from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models.entities import TocItem, Chunk


@dataclass
class LessonView:
    id: int
    title: str
    unit_id: int | None
    unit_title: str | None
    start_pdf_page: int | None
    end_pdf_page: int | None
    printed_page_start: int | None


def _compute_end_pages(items: list[TocItem]) -> dict[int, int | None]:
    ordered = sorted(items, key=lambda x: (x.order_index, x.id))
    ends: dict[int, int | None] = {it.id: it.end_pdf_page for it in ordered}
    for i, it in enumerate(ordered):
        if ends.get(it.id) is not None:
            continue
        sp = it.start_pdf_page
        if sp is None:
            continue
        nxt = None
        for j in range(i + 1, len(ordered)):
            if ordered[j].start_pdf_page is not None and ordered[j].start_pdf_page > sp:
                nxt = ordered[j].start_pdf_page
                break
        ends[it.id] = (nxt - 1) if nxt is not None else None
    return ends


def _is_unit(item: TocItem) -> bool:
    t = (item.title or "").strip()
    return item.level <= 1 or "الوحدة" in t


def get_units(db: Session, subject_id: int) -> list[TocItem]:
    items = (
        db.query(TocItem)
        .filter(TocItem.subject_id == subject_id)
        .order_by(TocItem.order_index.asc(), TocItem.id.asc())
        .all()
    )
    units = [it for it in items if _is_unit(it)]
    if units:
        return units
    # fallback: derive virtual units by scanning lessons without explicit parents.
    return [it for it in items if it.level <= 2][:12]


def get_lessons_for_unit(db: Session, subject_id: int, unit_id: int) -> list[LessonView]:
    items = (
        db.query(TocItem)
        .filter(TocItem.subject_id == subject_id)
        .order_by(TocItem.order_index.asc(), TocItem.id.asc())
        .all()
    )
    by_id = {x.id: x for x in items}
    unit = by_id.get(unit_id)
    if not unit:
        return []

    ends = _compute_end_pages(items)

    lessons: list[TocItem] = [x for x in items if x.parent_id == unit.id and x.id != unit.id]
    if not lessons:
        # fallback for flat TOC: take following non-unit items until next unit.
        ordered = sorted(items, key=lambda x: (x.order_index, x.id))
        uidx = next((i for i, x in enumerate(ordered) if x.id == unit.id), -1)
        if uidx >= 0:
            for x in ordered[uidx + 1 :]:
                if _is_unit(x):
                    break
                lessons.append(x)

    out: list[LessonView] = []
    for ls in lessons:
        out.append(
            LessonView(
                id=ls.id,
                title=ls.title,
                unit_id=unit.id,
                unit_title=unit.title,
                start_pdf_page=ls.start_pdf_page,
                end_pdf_page=ends.get(ls.id),
                printed_page_start=ls.printed_page_start,
            )
        )
    return out


def search_lessons(db: Session, subject_id: int, query: str, limit: int = 3) -> list[LessonView]:
    units = get_units(db, subject_id)
    unit_ids = {u.id for u in units}
    items = (
        db.query(TocItem)
        .filter(TocItem.subject_id == subject_id)
        .order_by(TocItem.order_index.asc(), TocItem.id.asc())
        .all()
    )
    ends = _compute_end_pages(items)
    by_id = {x.id: x for x in items}
    by_lesson: dict[int, tuple[int, TocItem]] = {}

    for it in items:
        if it.id in unit_ids:
            continue
        if it.level <= 1 and it.parent_id is None:
            continue
        score = fuzz.token_set_ratio(query, it.title)
        if score >= 20:
            by_lesson[it.id] = (score, it)

    # Fallback semantic-ish signal: score lessons using matching chunks content.
    if len(by_lesson) < limit:
        chunk_rows = (
            db.query(Chunk)
            .filter(Chunk.subject_id == subject_id, Chunk.toc_item_id.isnot(None))
            .limit(2500)
            .all()
        )
        for ch in chunk_rows:
            score = fuzz.token_set_ratio(query, (ch.content or "")[:400])
            if score < 35:
                continue
            lesson_id = int(ch.toc_item_id)
            toc = by_id.get(lesson_id)
            if not toc or toc.id in unit_ids:
                continue
            prev = by_lesson.get(lesson_id)
            if not prev or score > prev[0]:
                by_lesson[lesson_id] = (score, toc)

    ranked = sorted(by_lesson.values(), key=lambda x: x[0], reverse=True)[:limit]
    out: list[LessonView] = []
    for _, it in ranked:
        unit = by_id.get(it.parent_id) if it.parent_id else None
        out.append(
            LessonView(
                id=it.id,
                title=it.title,
                unit_id=unit.id if unit else None,
                unit_title=unit.title if unit else None,
                start_pdf_page=it.start_pdf_page,
                end_pdf_page=ends.get(it.id),
                printed_page_start=it.printed_page_start,
            )
        )

    # Last-resort: return first lessons so user can continue instead of hard fail.
    if not out:
        for it in items:
            if it.id in unit_ids:
                continue
            unit = by_id.get(it.parent_id) if it.parent_id else None
            out.append(
                LessonView(
                    id=it.id,
                    title=it.title,
                    unit_id=unit.id if unit else None,
                    unit_title=unit.title if unit else None,
                    start_pdf_page=it.start_pdf_page,
                    end_pdf_page=ends.get(it.id),
                    printed_page_start=it.printed_page_start,
                )
            )
            if len(out) >= limit:
                break

    return out[:limit]
