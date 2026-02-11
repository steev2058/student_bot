from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.entities import Subject, TocItem, Chunk
from app.services.rag_service import answer_question


def _db():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_answer_has_structured_citations():
    db = _db()
    subj = Subject(name_ar="فيزياء", code="physics", pdf_path="x")
    db.add(subj)
    db.commit()
    db.refresh(subj)

    unit = TocItem(subject_id=subj.id, title="الوحدة الأولى", level=1, order_index=1, start_pdf_page=0)
    db.add(unit)
    db.flush()
    lesson = TocItem(subject_id=subj.id, parent_id=unit.id, title="الدرس 1", level=2, order_index=2, start_pdf_page=1)
    db.add(lesson)
    db.flush()

    db.add(Chunk(subject_id=subj.id, toc_item_id=lesson.id, pdf_page_index=3, printed_page_number=12, content="النص العلمي عن الحركة"))
    db.commit()

    out = answer_question(db, user_id=1, subject_id=subj.id, question="الحركة", lesson_range=[0, 10])
    assert "المراجع" in out["answer"]
    assert "فيزياء" in out["answer"]
    assert "الوحدة الأولى / الدرس 1" in out["answer"]
    assert "PDF p4" in out["answer"]


def test_answer_refuses_without_retrieval():
    db = _db()
    subj = Subject(name_ar="رياضيات", code="math1", pdf_path="x")
    db.add(subj)
    db.commit()
    db.refresh(subj)

    out = answer_question(db, user_id=1, subject_id=subj.id, question="تفاضل", lesson_range=[0, 1])
    assert "لا أملك مراجع كافية" in out["answer"]
    assert out["citations"] == []
