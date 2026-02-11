from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.routes import router

setup_logging(settings.LOG_LEVEL)
app = FastAPI(title=settings.APP_NAME)
app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True, "app": settings.APP_NAME}
