import secrets
from sqlalchemy.orm import Session
from app.models.entities import Coupon, Redemption, Subscription, SubjectUnlock, Subject, User


def generate_coupons(db: Session, kind: str, count: int, subject_code: str | None = None):
    out = []
    for _ in range(count):
        code = f"EDU-{secrets.token_hex(4).upper()}"
        db.add(Coupon(code=code, kind=kind, subject_code=subject_code, is_used=False))
        out.append(code)
    db.commit()
    return out


def redeem_coupon(db: Session, telegram_id: int, code: str):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    c = db.query(Coupon).filter(Coupon.code == code, Coupon.is_used == False).first()  # noqa: E712
    if not c:
        return False, "كود غير صالح أو مستخدم"
    c.is_used = True
    db.add(Redemption(coupon_id=c.id, user_id=user.id))
    if c.kind == "subscription":
        db.merge(Subscription(user_id=user.id, active=True))
    elif c.kind == "subject_unlock" and c.subject_code:
        s = db.query(Subject).filter(Subject.code == c.subject_code).first()
        if s:
            db.merge(SubjectUnlock(user_id=user.id, subject_id=s.id))
    db.commit()
    return True, "تم التفعيل بنجاح"
