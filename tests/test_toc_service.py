from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.entities import Subject, TocItem
from app.services.toc_service import get_units, get_lessons_for_unit, search_lessons


def _db():
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return Session()


def test_units_lessons_and_search():
    db = _db()
    subj = Subject(name_ar="فيزياء", code="physics", pdf_path="x")
    db.add(subj)
    db.commit()
    db.refresh(subj)

    unit = TocItem(subject_id=subj.id, title="الوحدة الأولى", level=1, order_index=1, start_pdf_page=0)
    db.add(unit)
    db.flush()
    l1 = TocItem(subject_id=subj.id, parent_id=unit.id, title="الدرس 1: الحركة", level=2, order_index=2, start_pdf_page=3)
    l2 = TocItem(subject_id=subj.id, parent_id=unit.id, title="الدرس 2: القوة", level=2, order_index=3, start_pdf_page=8)
    db.add_all([l1, l2])
    db.commit()

    units = get_units(db, subj.id)
    assert len(units) == 1

    lessons = get_lessons_for_unit(db, subj.id, unit.id)
    assert len(lessons) == 2
    assert lessons[0].end_pdf_page == 7

    found = search_lessons(db, subj.id, "قوة", limit=3)
    assert found
    assert "القوة" in found[0].title
