from __future__ import annotations

import json
import subprocess
from pathlib import Path

DIAG_PATH = Path("artifacts/pdf_text_diagnosis.json")
SRC_DIRS = [Path("data/pdfs"), Path("/data/pdfs")]
OCR_DIR = Path("/data/pdfs_ocr")
OCR_DIR.mkdir(parents=True, exist_ok=True)


def find_pdf(filename: str) -> Path | None:
    for d in SRC_DIRS:
        p = d / filename
        if p.exists():
            return p
    return None


def run_ocr(inp: Path, out: Path) -> None:
    cmd = [
        "ocrmypdf",
        "--language",
        "ara",
        "--deskew",
        "--clean",
        "--optimize",
        "1",
        "--force-ocr",
        str(inp),
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    if not DIAG_PATH.exists():
        raise SystemExit("Run scripts/pdf_text_quality_diagnosis.py first")

    data = json.loads(DIAG_PATH.read_text(encoding="utf-8"))
    outputs = {}
    for code, info in data.items():
        category = info.get("category")
        filename = Path(info["path"]).name
        src = find_pdf(filename)
        if not src:
            outputs[code] = {"status": "missing_source"}
            continue

        out = OCR_DIR / filename
        if category in {"A", "B"}:
            run_ocr(src, out)
            outputs[code] = {"status": "ocr_done", "src": str(src), "out": str(out)}
        else:
            outputs[code] = {"status": "skipped_text_ok", "src": str(src)}

    Path("artifacts/pdf_ocr_results.json").write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
