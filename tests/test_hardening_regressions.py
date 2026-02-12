import io
import json
import logging
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.logging import setup_logging
from app.db.base import Base
from app.models.entities import Chunk, EventLog, Subject, TocItem
from app.services.rag_service import answer_question
from app.services.rate_limit import check_limit_with_meta


def _db():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def _seed_physics(db):
    subj = Subject(name_ar="فيزياء", code="physics", pdf_path="x")
    db.add(subj)
    db.commit()
    db.refresh(subj)

    unit = TocItem(subject_id=subj.id, title="الوحدة الأولى", level=1, order_index=1, start_pdf_page=1)
    db.add(unit)
    db.flush()
    lesson = TocItem(subject_id=subj.id, parent_id=unit.id, title="الحركة", level=2, order_index=2, start_pdf_page=1, end_pdf_page=5)
    db.add(lesson)
    db.flush()

    db.add_all([
        Chunk(subject_id=subj.id, toc_item_id=lesson.id, pdf_page_index=2, printed_page_number=10, content="الحركة هي تغير موضع الجسم مع الزمن."),
        Chunk(subject_id=subj.id, toc_item_id=lesson.id, pdf_page_index=3, printed_page_number=11, content="السرعة المتوسطة تساوي المسافة على الزمن."),
    ])
    db.commit()
    return subj.id


def test_lesson_restriction_refuses_unrelated_math_question():
    db = _db()
    subject_id = _seed_physics(db)

    out = answer_question(db, user_id=1, subject_id=subject_id, question="احسب مشتقة دالة كثيرة الحدود", lesson_range=[1, 5])

    assert "لا أملك مراجع كافية" in out["answer"]
    assert out.get("citations", []) == []


def test_hallucination_guard_for_out_of_book_question():
    db = _db()
    subject_id = _seed_physics(db)

    out = answer_question(db, user_id=2, subject_id=subject_id, question="ما عاصمة اليابان؟", lesson_range=[1, 5])

    assert "لا أملك مراجع كافية" in out["answer"]
    assert out.get("citations", []) == []


def test_cache_hit_and_latency_signal():
    db = _db()
    subject_id = _seed_physics(db)

    t1 = time.perf_counter()
    out1 = answer_question(db, user_id=3, subject_id=subject_id, question="الحركة", lesson_range=[1, 5])
    d1 = time.perf_counter() - t1

    t2 = time.perf_counter()
    out2 = answer_question(db, user_id=3, subject_id=subject_id, question="الحركة", lesson_range=[1, 5])
    d2 = time.perf_counter() - t2

    assert out1.get("cached") is False
    assert out2.get("cached") is True
    assert d2 <= d1


def test_rate_limit_returns_minutes_left():
    db = _db()
    user_id = 999
    ok, m = check_limit_with_meta(db, user_id, "global", 1, 600)
    assert ok is True and m == 0

    ok2, m2 = check_limit_with_meta(db, user_id, "global", 1, 600)
    assert ok2 is False
    assert m2 >= 1


def test_structured_json_logging_has_required_fields():
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers = []
    setup_logging("INFO")
    # Replace output stream for deterministic capture.
    for h in root.handlers:
        h.stream = stream

    logging.getLogger("hardening-test").info("hello")
    data = json.loads(stream.getvalue().strip())
    for key in ["asctime", "levelname", "name", "message", "funcName", "lineno"]:
        assert key in data


def test_event_logs_write_confirmed():
    db = _db()
    db.add(EventLog(user_id=None, event_type="q:1", payload="test"))
    db.commit()
    count = db.query(EventLog).filter(EventLog.event_type == "q:1").count()
    assert count == 1
