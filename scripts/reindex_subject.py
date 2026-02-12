import sys
from app.db.session import SessionLocal
from app.ingest.pipeline import ingest_subject
from app.core.config import settings

MAP = {
    "physics": ("فيزياء", "data/pdfs/physics.pdf"),
    "math1": ("رياضيات 1", "data/pdfs/math1.pdf"),
    "math2": ("رياضيات 2", "data/pdfs/math2.pdf"),
    "science": ("علوم", "data/pdfs/science.pdf"),
}

if len(sys.argv) < 2 or sys.argv[1] not in MAP:
    raise SystemExit("Usage: python scripts/reindex_subject.py physics|math1|math2|science")

code = sys.argv[1]
name_ar, path = MAP[code]
with SessionLocal() as db:
    print(ingest_subject(db, code, name_ar, path, settings.CONTENT_VERSION))
