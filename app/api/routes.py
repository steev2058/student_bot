from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.rate_limit import check_limit
from app.services.rag_service import answer_question

router = APIRouter(prefix="/api")


@router.post("/ask")
def ask(payload: dict, db: Session = Depends(get_db)):
    user_id = int(payload.get("user_id", 0))
    if not check_limit(db, user_id, "global", 30, 600):
        raise HTTPException(status_code=429, detail="تم تجاوز الحد المسموح. حاول لاحقاً.")
    q = payload.get("question", "")
    subject_id = int(payload.get("subject_id", 0))
    lesson_range = payload.get("lesson_range")
    username = payload.get("username", "")
    watermark = payload.get("watermark") or (f"User: @{username} / id: {user_id}" if username else f"User: unknown / id: {user_id}")
    out = answer_question(db, user_id, subject_id, q, lesson_range, watermark=watermark)
    return out
