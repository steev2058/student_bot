# OCR + Reindex Results

Date: 2026-02-12 (UTC)

## Commands Executed

### Dependencies
```bash
apt-get update
apt-get install -y tesseract-ocr tesseract-ocr-ara ocrmypdf
```
Result: packages already present.

### OCR attempts
```bash
# full OCR attempt (stopped due runtime constraints on large files)
ocrmypdf -l ara --force-ocr /data/pdfs/<subject>.pdf /data/pdfs_ocr/<subject>.pdf

# page-scoped attempt (1,5,10,20) also hit long post-processing on very large inputs
ocrmypdf -l ara --force-ocr --pages 1,5,10,20 /data/pdfs/<subject>.pdf /data/pdfs_ocr/<subject>.pdf
```
Status: **not fully completed** for full target PDFs (`physics/math1/math2`) in this run; no finalized files produced yet under `/data/pdfs_ocr`.

### DB init + reindex
```bash
DATABASE_URL=sqlite:///./artifacts/reindex.db python scripts/init_db.py
for s in physics math1 math2; do
  DATABASE_URL=sqlite:///./artifacts/reindex.db PDF_USE_OCR=false python scripts/reindex_subject.py $s
done
```

Reindex output:
- physics: `toc_items=29`
- math1: `toc_items=25`
- math2: `toc_items=22`

## Before/After Metrics (sample pages 1,5,10,20)
- **Before OCR:** documented in `reports/pdf_text_diagnosis.md` (all A)
- **After OCR:** unavailable in this run because OCR jobs did not complete to output files.

## Validation

### TOC counts
- physics: units=6, lessons=23, chunks=267
- math1: units=5, lessons=20, chunks=231
- math2: units=5, lessons=17, chunks=196

✅ TOC counts non-zero for all target subjects.

### Explain responses with citations/page refs
Queries checked: `نيوتن`, `التكامل`, `التيار`

Result: retrieval returned 0 for these checks on current indexed text, so explanations with citations/page refs were **not** produced for these keywords in this run.

### Smart search top3
- physics/`نيوتن`: 0
- math1/`التكامل`: 0
- physics/`التيار`: 0

❌ top3 validation failed for target terms on current corpus state.

## Code Changes Implemented
- Added layout-aware page extraction ordering by `(y, x)`.
- Added Arabic normalization in ingestion:
  - remove tashkeel
  - normalize `أ/إ/آ -> ا`
  - `ى -> ي`
  - consistent `ة -> ه`
- Added word-based chunking with bounds and overlap:
  - min 300 words
  - max 700 words
  - overlap 90 words
- Preserved metadata in chunks:
  - `pdf_page_index`
  - `printed_page_number` (via TOC page mapping reverse lookup)
- OCR config wiring:
  - `PDF_USE_OCR`
  - `PDF_OCR_DIR`
  - ingestion prefers OCR file when enabled + available, else falls back to original.
- Added regression tests:
  - `test_pdf_text_quality()`
  - `test_citations_present()`

## Residual Risks
1. OCR output generation for large PDFs is runtime-heavy; without completed OCR outputs, retrieval quality remains poor for core Arabic curriculum terms.
2. Citation + smart-search validations for (`نيوتن/التكامل/التيار`) remain failing on current indexed text and require completed OCR pipeline to pass reliably.
3. Normalization choice (`ة -> ه`) can reduce lexical matching unless query normalization is consistently applied (now wired in retrieval).
