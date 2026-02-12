from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz

PDF_MAP = {
    "physics": "physics.pdf",
    "math1": "math1.pdf",
    "math2": "math2.pdf",
}

SAMPLE_PAGES_1_BASED = [1, 5, 10, 20]
AR_RE = re.compile(r"[\u0600-\u06FF]")
LETTER_RE = re.compile(r"[A-Za-z\u0600-\u06FF]")


def pick_pdf_path(filename: str) -> Path:
    candidates = [
        Path("data/pdfs") / filename,
        Path("/data/pdfs") / filename,
        Path("/data/pdfs_ocr") / filename,
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(filename)


def compute_ratios(text: str) -> tuple[float, float, int]:
    letters = LETTER_RE.findall(text)
    letter_count = len(letters)
    arabic_count = len(AR_RE.findall(text))
    non_alnum = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
    total = max(1, len(text))
    arabic_ratio = (arabic_count / max(1, letter_count))
    gibberish_ratio = non_alnum / total
    return arabic_ratio, gibberish_ratio, len(text)


def classify(samples: list[dict[str, Any]]) -> str:
    low_text_pages = sum(1 for s in samples if s["text_len"] < 30)
    if low_text_pages >= max(2, len(samples) - 1):
        return "A"

    avg_ar = sum(s["arabic_char_ratio"] for s in samples) / max(1, len(samples))
    avg_gib = sum(s["gibberish_ratio"] for s in samples) / max(1, len(samples))
    if avg_ar < 0.35 or avg_gib > 0.20:
        return "B"
    return "C"


def main() -> None:
    rows: dict[str, Any] = {}
    for code, fname in PDF_MAP.items():
        path = pick_pdf_path(fname)
        doc = fitz.open(path)
        samples = []
        for p1 in SAMPLE_PAGES_1_BASED:
            idx = p1 - 1
            if idx < 0 or idx >= doc.page_count:
                continue
            page = doc[idx]
            text = page.get_text("text") or ""
            blocks = page.get_text("blocks") or []
            ar, gib, ln = compute_ratios(text)
            samples.append(
                {
                    "page": p1,
                    "text_len": ln,
                    "arabic_char_ratio": round(ar, 4),
                    "gibberish_ratio": round(gib, 4),
                    "blocks_count": len(blocks),
                }
            )
        category = classify(samples)
        rows[code] = {
            "path": str(path),
            "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
            "samples": samples,
            "category": category,
        }

    Path("artifacts").mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(parents=True, exist_ok=True)
    Path("artifacts/pdf_text_diagnosis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# PDF Arabic Text Diagnosis", ""]
    legend = {
        "A": "Scanned / near-empty text extraction (OCR required)",
        "B": "Text exists but likely broken encoding/RTL (OCR preferred)",
        "C": "Text quality acceptable; extraction/chunking likely issue",
    }
    for code, data in rows.items():
        lines.append(f"## {code}")
        lines.append(f"- Path: `{data['path']}`")
        lines.append(f"- Size: {data['size_mb']} MB")
        lines.append(f"- Category: **{data['category']}** — {legend[data['category']]}")
        lines.append("- Samples:")
        for s in data["samples"]:
            lines.append(
                f"  - p{s['page']}: len={s['text_len']}, ar_ratio={s['arabic_char_ratio']}, gib={s['gibberish_ratio']}, blocks={s['blocks_count']}"
            )
        lines.append("")

    Path("reports/pdf_text_diagnosis.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote reports/pdf_text_diagnosis.md")


if __name__ == "__main__":
    main()
