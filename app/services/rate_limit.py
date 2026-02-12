from datetime import datetime, timedelta
import math
from sqlalchemy.orm import Session
from app.models.entities import RateLimitBucket


def check_limit_with_meta(db: Session, user_id: int, bucket: str, max_count: int, window_sec: int) -> tuple[bool, int]:
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
        return True, 0
    if row.count >= max_count:
        sec_left = max(0, int((row.window_start + timedelta(seconds=window_sec) - now).total_seconds()))
        return False, int(math.ceil(sec_left / 60))
    row.count += 1
    db.commit()
    return True, 0


def check_limit(db: Session, user_id: int, bucket: str, max_count: int, window_sec: int) -> bool:
    ok, _ = check_limit_with_meta(db, user_id, bucket, max_count, window_sec)
    return ok
