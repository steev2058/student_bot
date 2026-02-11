from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.entities import RateLimitBucket


def check_limit(db: Session, user_id: int, bucket: str, max_count: int, window_sec: int) -> bool:
    now = datetime.utcnow()
    start = now - timedelta(seconds=window_sec)
    row = (
        db.query(RateLimitBucket)
        .filter(RateLimitBucket.user_id == user_id, RateLimitBucket.bucket == bucket)
        .order_by(RateLimitBucket.window_start.desc())
        .first()
    )
    if row is None or row.window_start < start:
        row = RateLimitBucket(user_id=user_id, bucket=bucket, window_start=now, count=1)
        db.add(row)
        db.commit()
        return True
    if row.count >= max_count:
        return False
    row.count += 1
    db.commit()
    return True
