# Verification & Hardening Report — 2026-02-12

## Scope
Autonomous full pass for phases 0–4 on `student_bot`.

## Phase 0 — Baseline & Env Presence
- Git HEAD: `ec552ae`.
- Docker: `db` and `api` running (`docker compose ps` in artifacts).
- Health: `GET /health` => `{"ok":true,"app":"student-bot"}`.
- API logs tail captured.
- Env key presence (existence-only):
  - `TELEGRAM_BOT_TOKEN`: **No** (env + file), project uses `BOT_TOKEN`.
  - `PDF_*`: **Yes** (in env files).
  - DB connection keys: **Yes** (in env files).

Artifacts:
- `artifacts/phase0_git_rev.txt`
- `artifacts/phase0_git_status.txt`
- `artifacts/phase0_docker_ps.txt`
- `artifacts/phase0_docker_logs_api.txt`
- `artifacts/phase0_curl_health.txt`
- `artifacts/phase0_env_presence.json`

## Phase 1 — PDFs, DB TOC Integrity, Mapping, TOC Parse
### PDF inventory
Detected PDFs with sizes under `/data/pdfs` (and mirrored project path):
- physics.pdf: 248,446,531 bytes
- math1.pdf: 123,320,505 bytes
- math2.pdf: 209,906,874 bytes

### DB checks
- Subjects count: **3**.
- TOC counts per subject and range validity (start/end pages):
  - physics: 29 items, 26 valid ranges
  - math1: 25 items, 22 valid ranges
  - math2: 22 items, 18 valid ranges
- Printed pages presence (`printed_page_start`) in TOC: **0** across all subjects.

### Mapping validation (random 3 lessons per subject, ±2 pages)
- Executed for each subject (3/subject).
- Result: 0 matched by automatic text match heuristic (likely OCR/text extraction mismatch and/or title normalization mismatch in PDFs).

### TOC JSON parseability
- `data/toc/physics.json`: parseable
- `data/toc/math1.json`: parseable
- `data/toc/math2.json`: parseable

### TOC Quality Score (computed)
Formula used: `0.5*valid_range_ratio + 0.2*printed_page_ratio + 0.3*sample_match_ratio`.
- physics: **44.83**
- math1: **44.00**
- math2: **40.91**

Artifact:
- `artifacts/phase1_data_quality.json`

## Phase 2 — RAG Correctness & Citation Integrity (+ hardening)
### Test execution
- Existing suite baseline passed.
- Added regression tests for:
  1. Citation/structured answer behavior
  2. Lesson restriction (physics context + math question)
  3. Hallucination guard for out-of-book question

### Findings
- Initial behavior allowed off-topic answers in some cases.

### Fixes applied
1. **RAG retrieval guard hardening** (`app/services/rag_service.py`)
   - Added lexical-overlap guard on meaningful query terms.
   - Enforced thresholding to return empty retrieval when off-topic.
   - Ranking now uses overlap + fuzzy + semantic score.
2. **Regression tests added** (`tests/test_hardening_regressions.py`)
   - Unrelated math question in physics context => refusal/no citations.
   - Out-of-book question => refusal/no citations.
   - Cache hit behavior + latency direction.

### Result
- Full test run: **12 passed**.
- Artifacts:
  - `artifacts/phase2_pytest_initial.txt`
  - `artifacts/phase2_phase4_pytest_after.txt`

## Phase 3 — Bot UX E2E Logical Verification (simulation)
Validated logically (service-driven simulation + DB state checks) without real Telegram UI.
Covered:
- start→grade→subject→plan→unit→lesson path feasibility (units/lessons resolvable).
- search keyword→top3 suggestions.
- lesson open and explain call path.
- demo limit (10 questions/subject) enforcement before AI and persistence via `event_logs` count.

Result snapshot:
- units + lessons available in all 3 subjects.
- search top3 returns 3 suggestions.
- demo-limit simulation: `used=10`, `blocked_before_ai=true`, persisted in DB.

Artifact:
- `artifacts/phase3_e2e_simulation.json`

## Phase 4 — Rate Limit, Cache, Logging, Event Logs
### Rate limit behavior (Arabic throttle + minutes_left)
- Implemented metadata-capable limiter (`check_limit_with_meta`).
- Bot now returns friendly Arabic throttle message with `minutes_left`.
- Verified via tests.

### Cache behavior + latency evidence
- Repeated explain request: first call uncached, second cached.
- Example evidence: first ~29.43ms vs second ~2.34ms.

### Logging structure
- JSON logging includes required fields: `asctime`, `levelname`, `name`, `message`, `funcName`, `lineno`.

### event_logs writes
- Confirmed writes exist in DB (`event_logs_count=16` at check time).

Artifacts:
- `artifacts/phase4_cache_latency.json`
- `artifacts/phase4_logging_check.json`
- `artifacts/phase4_event_logs_count.txt`

---

## Pass/Fail Matrix
- Phase 0 baseline capture: **PASS**
- Phase 0 env presence checks: **PASS** (with note: token key naming mismatch to requested key)
- Phase 1 PDF/DB/TOC parse checks: **PASS**
- Phase 1 mapping quality: **PARTIAL/FAIL** (0/3 random matches per subject by heuristic)
- Phase 2 RAG correctness+citation integrity: **PASS after fixes**
- Phase 3 UX logical E2E coverage: **PASS (logical simulation)**
- Phase 4 rate limit minutes_left: **PASS after fix**
- Phase 4 cache hit+latency evidence: **PASS**
- Phase 4 structured logging fields: **PASS**
- Phase 4 event_logs writes: **PASS**

## Residual Risks
1. TOC-to-PDF heading auto-match weak (likely OCR/text normalization limits); manual/semantic mapping validation recommended.
2. `TELEGRAM_BOT_TOKEN` key absent; project currently depends on `BOT_TOKEN`.
3. API route still uses generic limiter response (no `minutes_left` in HTTP 429 body); bot path is fixed.
