# Student Bot — الثالث الثانوي العلمي

FastAPI + Telegram bot (aiogram) + Postgres/pgvector + Alembic + Docker Compose.

## Features
- Arabic Telegram UX for grade/subject/action flow.
- TOC extraction fallback chain:
  1) outlines/bookmarks (pypdf)
  2) TOC pages by Arabic keywords + page-number parsing
  3) heading/font-size heuristic
- TOC debug export: `data/toc/<subject>.json`
- Ingestion pipeline with page-bounded chunk metadata:
  `subject_id, pdf_page_index, printed_page_number, toc_item_id`
- Lesson embeddings (deterministic fallback if no model key)
- Retrieval constrained to selected lesson range + mandatory citations
- Coupons MVP for subscription and subject unlock
- Rate limits (DB-backed): global `30/10m`, AI-heavy `10/10m`
- Caching:
  - explanation cache TTL 30 days
  - retrieval cache TTL 7 days (key includes content_version)
- Structured JSON logging for API and bot

## Project Structure
- `app/main.py` FastAPI app
- `app/bot/runner.py` Telegram bot
- `app/ingest/*` PDF download + TOC + ingestion
- `app/services/*` RAG, cache, coupons, rate-limit
- `app/models/entities.py` schema
- `alembic/versions/0001_initial.py` initial migration

## Environment
Copy `.env.example` to `.env` and set:
- `DATABASE_URL`
- `BOT_TOKEN`
- `OPENAI_API_KEY` (optional; deterministic fallback active if empty)
- PDF URLs (`PDF_PHYSICS_URL`, `PDF_MATH1_URL`, `PDF_MATH2_URLS`)

## Run with Docker Compose
```bash
docker compose up -d db
docker compose run --rm api python scripts/init_db.py
docker compose run --rm api python scripts/load_pdfs.py
# Reindex per subject:
docker compose run --rm api python scripts/reindex_subject.py physics
docker compose run --rm api python scripts/reindex_subject.py math1
docker compose run --rm api python scripts/reindex_subject.py math2

docker compose up -d api bot
```

API health: `GET http://localhost:8000/health`

## Polling/Webhook
- Polling is default (`python -m app.bot.runner`)
- Webhook variables are present for production wiring (`USE_WEBHOOK`, `WEBHOOK_BASE_URL`)

## Telegram UX Flow
- `/start` -> grade `الثالث الثانوي - علمي`
- subject: `فيزياء / رياضيات 1 / رياضيات 2`
- actions:
  - خطة الكتاب
  - بحث داخل الكتاب
  - شرح الدرس
  - اختبار سريع
  - اختبار امتحاني
  - اسأل سؤال ضمن الدرس

## Coupons and Gating
Admin commands:
- `/admin_gen_coupons subscription 10`
- `/admin_gen_coupons subject_unlock 20 physics`
- `/admin_reindex` (operator hint)

User:
- `/redeem CODE`

Free-demo policy hooks implemented in DB/session layer; apply business rules in bot handlers (1 lesson + 10 questions/subject).

## Content Protection
See `docs/content_protection.md`.
Paid answers should append:
`User: @username / id: <id>`

## Smoke Test (local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install .
python scripts/init_db.py
pytest -q
```

## Notes
- If model/API key missing, deterministic embedding/retrieval remains functional for local testing.
- Reindex should bump `CONTENT_VERSION` to invalidate caches.
