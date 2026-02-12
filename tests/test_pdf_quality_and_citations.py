from app.ingest.pdf_text_utils import compute_text_quality_metrics, classify_pdf_quality
from app.services.rag_service import answer_question
from app.db.base import Base
from app.models.entities import Subject, TocItem, Chunk

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _db():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_pdf_text_quality():
    healthy_text = " ".join(["النص"] * 500)
    noisy_text = "%%%%%% $$$$$$ abcdefghijklmnop"

    healthy_metrics = compute_text_quality_metrics(healthy_text)
    noisy_metrics = compute_text_quality_metrics(noisy_text)

    assert healthy_metrics["text_len"] > 1000
    assert healthy_metrics["arabic_char_ratio"] > 0.7
    assert noisy_metrics["gibberish_ratio"] >= 0.0

    cat = classify_pdf_quality([
        healthy_metrics,
        healthy_metrics,
        {"text_len": 180.0, "arabic_char_ratio": 0.75, "gibberish_ratio": 0.01},
    ])
    assert cat in {"B", "C"}


def test_citations_present():
    db = _db()
    subj = Subject(name_ar="فيزياء", code="physics", pdf_path="x")
    db.add(subj)
    db.commit()
    db.refresh(subj)

    unit = TocItem(subject_id=subj.id, title="الوحدة الأولى", level=1, order_index=1, start_pdf_page=0)
    db.add(unit)
    db.flush()

    lesson = TocItem(
        subject_id=subj.id,
        parent_id=unit.id,
        title="قوانين نيوتن",
        level=2,
        order_index=2,
        start_pdf_page=1,
        end_pdf_page=20,
    )
    db.add(lesson)
    db.flush()

    db.add(Chunk(subject_id=subj.id, toc_item_id=lesson.id, pdf_page_index=4, printed_page_number=13, content="قانون نيوتن الاول يصف القصور الذاتي"))
    db.commit()

    out = answer_question(db, user_id=10, subject_id=subj.id, question="اشرح قانون نيوتن الأول", lesson_range=[0, 20])
    answer = out["answer"]
    assert "المراجع" in answer
    assert "PDF p5" in answer
    assert "ص13" in answer
