#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import requests

URL = "https://curricula.moed.gov.sy/curricula-2026-2025/12/12-science.pdf"
TARGETS = [
    Path("/data/pdfs/science.pdf"),
    Path("data/pdfs/science.pdf"),
]
TMP = Path("/tmp/science.pdf.download")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)

    # Primary path: curl with retries (more robust on this host for moed.gov.sy)
    curl_cmd = [
        "curl",
        "-fL",
        "--retry",
        "6",
        "--retry-delay",
        "2",
        "--connect-timeout",
        "20",
        "-o",
        str(out),
        url,
    ]
    r = subprocess.run(curl_cmd)
    if r.returncode == 0 and out.exists() and out.stat().st_size > 1024 * 1024:
        return

    # Fallback: requests stream
    with requests.get(url, stream=True, timeout=90) as rr:
        rr.raise_for_status()
        with out.open("wb") as f:
            for chunk in rr.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def main() -> None:
    download(URL, TMP)
    size_mb = TMP.stat().st_size / (1024 * 1024)
    digest = sha256_file(TMP)

    for t in TARGETS:
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TMP, t)

    print("✅ Download complete")
    print(f"URL: {URL}")
    print(f"Size: {size_mb:.2f} MB")
    print(f"SHA256: {digest}")
    print("Saved to:")
    for t in TARGETS:
        print(f"- {t}")


if __name__ == "__main__":
    main()
