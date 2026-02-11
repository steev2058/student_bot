from pathlib import Path
import httpx
from app.core.config import settings


def _download(url: str, target: Path) -> bool:
    if not url:
        return False
    try:
        r = httpx.get(url, timeout=40, follow_redirects=True)
        r.raise_for_status()
        target.write_bytes(r.content)
        return True
    except Exception:
        return False


def download_curriculum_pdfs(base_dir: str = "data/pdfs"):
    out = {}
    p = Path(base_dir)
    p.mkdir(parents=True, exist_ok=True)

    out["physics"] = _download(settings.PDF_PHYSICS_URL, p / "physics.pdf")
    out["math1"] = _download(settings.PDF_MATH1_URL, p / "math1.pdf")

    math2_urls = [u.strip() for u in settings.PDF_MATH2_URLS.split(",") if u.strip()]
    ok = False
    for u in math2_urls:
        if _download(u, p / "math2.pdf"):
            ok = True
            out["math2_url_used"] = u
            break
    out["math2"] = ok
    return out
