from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 从 .env 读取配置；extra="ignore" 允许 .env 有多余字段
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AIO Demo"

    # Demo 用 SQLite 异步驱动。切换 PostgreSQL 时改成：
    # postgresql+asyncpg://aio:pass@localhost:5432/aio
    DATABASE_URL: str = "sqlite+aiosqlite:///./aio_demo.db"
    ENABLE_VECTOR: bool = False

    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天


settings = Settings()
