from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.ingest.pdf_text_utils import compute_text_quality_metrics, classify_pdf_quality
from app.services.rag_service import answer_question
from app.models.entities import Subject, TocItem, Chunk


def _db():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_pdf_text_quality_thresholds_sanity():
    good = "هذا نص عربي واضح يحتوي على كلمات مفهومة في درس الفيزياء والحركه والطاقه."
    m = compute_text_quality_metrics(good)
    assert m["text_len"] > 20
    assert m["arabic_char_ratio"] > 0.5

    cat = classify_pdf_quality([
        {"text_len": 300.0, "arabic_char_ratio": 0.7, "gibberish_ratio": 0.03},
        {"text_len": 280.0, "arabic_char_ratio": 0.68, "gibberish_ratio": 0.04},
    ])
    assert cat == "C"


def test_citations_present():
    db = _db()
    s = Subject(code="physics", name_ar="فيزياء", pdf_path="x.pdf", content_version=1)
    db.add(s)
    db.flush()

    u = TocItem(subject_id=s.id, title="الوحدة 1", level=1, order_index=1, start_pdf_page=1)
    db.add(u)
    db.flush()

    l = TocItem(subject_id=s.id, parent_id=u.id, title="الدرس 1", level=2, order_index=2, start_pdf_page=1, end_pdf_page=2)
    db.add(l)
    db.flush()

    c = Chunk(subject_id=s.id, toc_item_id=l.id, pdf_page_index=1, printed_page_number=10, content="قانون نيوتن الثاني ينص على أن القوة تساوي الكتلة في التسارع")
    db.add(c)
    db.commit()

    ans = answer_question(db, user_id=1, subject_id=s.id, question="ما هو قانون نيوتن الثاني؟", lesson_range=[1, 2], watermark=None)
    text = ans.get("answer", "")
    assert "المراجع" in text
    assert "PDF p" in text
