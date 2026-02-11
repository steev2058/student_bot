import hashlib
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.entities import CacheEntry


def make_cache_key(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode()).hexdigest()


def get_cache(db: Session, key: str):
    row = db.query(CacheEntry).filter(CacheEntry.cache_key == key).first()
    if not row:
        return None
    if row.expires_at < datetime.utcnow():
        db.delete(row)
        db.commit()
        return None
    return row.value


def set_cache(db: Session, key: str, value: str, ttl_days: int):
    exp = datetime.utcnow() + timedelta(days=ttl_days)
    row = db.query(CacheEntry).filter(CacheEntry.cache_key == key).first()
    if row:
        row.value = value
        row.expires_at = exp
    else:
        db.add(CacheEntry(cache_key=key, value=value, expires_at=exp))
    db.commit()
