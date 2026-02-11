import json
import re
from pathlib import Path
import fitz
from pypdf import PdfReader

AR_TOC_KEYWORDS = ["الفهرس", "المحتويات", "الوحدة", "الدرس"]


def extract_from_outlines(pdf_path: str):
    try:
        reader = PdfReader(pdf_path)
        out = []
        def walk(items, level=1):
            for it in items:
                if isinstance(it, list):
                    walk(it, level + 1)
                else:
                    title = getattr(it, "title", "").strip()
                    page = reader.get_destination_page_number(it) if hasattr(reader, "get_destination_page_number") else None
                    if title:
                        out.append({"title": title, "level": level, "page": page})
        walk(reader.outline)
        return out
    except Exception:
        return []


def extract_from_toc_pages(pdf_path: str):
    doc = fitz.open(pdf_path)
    items = []
    pattern = re.compile(r"(.+?)\s+([0-9]{1,3})$")
    for i in range(min(25, doc.page_count)):
        text = doc[i].get_text("text")
        if any(k in text for k in AR_TOC_KEYWORDS):
            for line in text.splitlines():
                m = pattern.search(line.strip())
                if m:
                    items.append({"title": m.group(1).strip(" ."), "printed_page": int(m.group(2)), "level": 2})
    return items


def extract_by_heading_heuristic(pdf_path: str):
    doc = fitz.open(pdf_path)
    items = []
    for i in range(doc.page_count):
        blocks = doc[i].get_text("dict").get("blocks", [])
        for b in blocks:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    t = s.get("text", "").strip()
                    if len(t) > 4 and s.get("size", 0) >= 14 and ("الدرس" in t or "الوحدة" in t):
                        items.append({"title": t, "level": 2, "page": i})
                        break
    return items


def compute_page_mapping(pdf_path: str):
    doc = fitz.open(pdf_path)
    mapping = {}
    num_pattern = re.compile(r"\b([0-9]{1,3})\b")
    for i in range(doc.page_count):
        text = doc[i].get_text("text")[-500:]
        nums = num_pattern.findall(text)
        if nums:
            mapping[int(nums[-1])] = i
    return mapping


def validate_toc_targets(toc_items, page_mapping):
    samples = toc_items[: min(5, len(toc_items))]
    validated = []
    for item in samples:
        p = item.get("printed_page")
        validated.append({"title": item.get("title"), "printed": p, "pdf": page_mapping.get(p) if p else item.get("page")})
    return validated


def extract_toc_with_fallback(pdf_path: str, subject_code: str, output_dir: str = "data/toc"):
    toc = extract_from_outlines(pdf_path)
    method = "A_outlines"
    if not toc:
        toc = extract_from_toc_pages(pdf_path)
        method = "B_toc_pages"
    if not toc:
        toc = extract_by_heading_heuristic(pdf_path)
        method = "C_heading_heuristic"

    mapping = compute_page_mapping(pdf_path)
    validated = validate_toc_targets(toc, mapping)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out = {"method": method, "items": toc, "page_mapping": mapping, "validation": validated}
    Path(output_dir, f"{subject_code}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
