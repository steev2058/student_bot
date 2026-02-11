from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "student-bot"
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str
    BOT_TOKEN: str = ""
    ADMIN_USER_IDS: str = ""
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    CHAT_MODEL: str = "gpt-4o-mini"
    PDF_PHYSICS_URL: str = ""
    PDF_MATH1_URL: str = ""
    PDF_MATH2_URLS: str = ""
    WEBHOOK_BASE_URL: str = ""
    USE_WEBHOOK: bool = False
    CONTENT_VERSION: int = 1


settings = Settings()  # type: ignore[call-arg]
