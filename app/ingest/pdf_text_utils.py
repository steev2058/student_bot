from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image
import pytesseract

from app.core.config import settings

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_WORD_RE = re.compile(r"\S+")
# Heuristic gibberish markers: replacement glyphs, long mixed tokens, or noisy symbol runs.
_GIBBERISH_TOKEN_RE = re.compile(r"\uFFFD|(?:[A-Za-z0-9]{14,})|(?:[^\w\s\u0600-\u06FF]{6,})")
_TASHKEEL_RE = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED]")


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = _TASHKEEL_RE.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي")
    # Normalize ta marbuta consistently to ha for stable retrieval matching.
    text = text.replace("ة", "ه")
    # Normalize Arabic punctuation variants.
    text = text.replace("ـ", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_page_text_layout_aware(page: Any) -> str:
    blocks = page.get_text("blocks") or []
    ordered = sorted(blocks, key=lambda b: (float(b[1]), float(b[0])))
    parts: list[str] = []
    for b in ordered:
        if len(b) >= 5:
            t = (b[4] or "").strip()
            if t:
                parts.append(t)

    text = "\n".join(parts) if parts else (page.get_text("text") or "")
    # OCR fallback for pages with near-empty text layer only (enabled via env).
    if settings.PDF_USE_OCR and len(text.strip()) < 8:
        try:
            pix = page.get_pixmap(matrix=None, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_text = pytesseract.image_to_string(img, lang="ara") or ""
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
        except Exception:
            pass
    return text


def chunk_text_words(text: str, min_words: int = 300, max_words: int = 700, overlap_words: int = 90) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    # Keep overlap within sane bounds to avoid degenerate chunks.
    overlap_words = max(0, min(overlap_words, max_words - 1))

    out: list[str] = []
    step = max(1, max_words - overlap_words)
    i = 0
    n = len(words)
    while i < n:
        j = min(n, i + max_words)
        chunk_words = words[i:j]
        # If final chunk is too short, append to previous chunk when possible.
        if len(chunk_words) < min_words and out:
            out[-1] = f"{out[-1]} {' '.join(chunk_words)}".strip()
            break
        out.append(" ".join(chunk_words))
        if j >= n:
            break
        i += step
    return out


def compute_text_quality_metrics(text: str) -> dict[str, float]:
    text = text or ""
    text_len = len(text)
    non_space = [c for c in text if not c.isspace()]
    arabic_chars = sum(1 for c in non_space if _ARABIC_CHAR_RE.match(c))
    arabic_char_ratio = arabic_chars / max(1, len(non_space))

    words = _WORD_RE.findall(text)
    gibberish_tokens = sum(1 for w in words if _GIBBERISH_TOKEN_RE.search(w))
    gibberish_ratio = gibberish_tokens / max(1, len(words))

    return {
        "text_len": float(text_len),
        "arabic_char_ratio": float(arabic_char_ratio),
        "gibberish_ratio": float(gibberish_ratio),
    }


def classify_pdf_quality(page_metrics: list[dict[str, float]]) -> str:
    if not page_metrics:
        return "A"
    avg_len = sum(m["text_len"] for m in page_metrics) / len(page_metrics)
    avg_ar = sum(m["arabic_char_ratio"] for m in page_metrics) / len(page_metrics)
    avg_gib = sum(m["gibberish_ratio"] for m in page_metrics) / len(page_metrics)

    # A: likely scanned or missing text layer.
    if avg_len < 120 or avg_ar < 0.25:
        return "A"
    # B: text exists but still noisy.
    if avg_len < 250 or avg_gib > 0.15:
        return "B"
    return "C"
