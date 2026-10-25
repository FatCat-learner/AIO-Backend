import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# 出厂默认密钥，prod 环境下出现这个值就拒绝启动
DEFAULT_SECRET_KEY = "change-me-in-production"


class Settings(BaseSettings):
    # 从 .env 读取配置；extra="ignore" 允许 .env 有多余字段
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "AIO Demo"

    # 运行环境：dev / test / prod。只有显式写 prod 才启用生产校验，
    # 所以本地开发不受影响；上线部署时必须在 .env 里设 ENV=prod
    ENV: str = "dev"
    # 控制 SQL 回显等调试输出。prod 下请设 DEBUG=false
    DEBUG: bool = True

    # Demo 用 SQLite 异步驱动。切换 PostgreSQL 时改成：
    # postgresql+asyncpg://aio:pass@localhost:5432/aio
    DATABASE_URL: str = "sqlite+aiosqlite:///./aio_demo.db"
    ENABLE_VECTOR: bool = False

    # MCP 调试服务器（streamable-http，端点 /mcp），能直接读写数据库且没有鉴权。
    # 默认关闭：需要 curl / 别的客户端调 /mcp 时在 .env 里设 MCP_ENABLED=true。
    # DSH 走的是 scripts/mcp_stdio.py（stdio），不受这个开关影响
    MCP_ENABLED: bool = False

    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    # 开发便利账号：启动时保证 DEV_ADMIN_USERNAME / DEV_ADMIN_PASSWORD 一定可登录
    # （不存在就建号，密码被改过或被禁用就重置回来）。上线前在 .env 里设 false。
    DEV_SEED_ADMIN: bool = True
    DEV_ADMIN_USERNAME: str = "admin"
    DEV_ADMIN_PASSWORD: str = "12345"

    # 允许跨域的前端来源，逗号分隔。* 只适合本地调试
    CORS_ORIGINS: str = (
        "http://localhost:5173,"
        "http://localhost:9527,"
        "http://localhost:9528,"
        "http://127.0.0.1:5173,"
        "http://127.0.0.1:9527,"
        "http://127.0.0.1:9528"
    )

    @property
    def is_prod(self) -> bool:
        return self.ENV.strip().lower() in ("prod", "production")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]


settings = Settings()


def validate_settings() -> None:
    """启动时的配置体检。

    - dev：只告警，不打断本地开发
    - prod：危险默认值直接拒绝启动，避免把调试入口带上线
    """
    weak_key = (
        settings.SECRET_KEY == DEFAULT_SECRET_KEY
        or len(settings.SECRET_KEY) < 32
    )

    if settings.is_prod:
        problems: list[str] = []
        if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY 仍是出厂默认值，请改成随机长串")
        elif len(settings.SECRET_KEY) < 32:
            problems.append("SECRET_KEY 少于 32 字节，HS256 强度不足")
        if settings.MCP_ENABLED:
            problems.append("MCP_ENABLED=true：/mcp 无鉴权且可任意读写库，prod 必须关")
        if settings.DEV_SEED_ADMIN:
            problems.append("DEV_SEED_ADMIN=true：每次启动重置开发账号，prod 必须关")
        if problems:
            raise RuntimeError(
                "生产环境配置不安全，拒绝启动：\n  - " + "\n  - ".join(problems)
            )
        return

    if weak_key:
        logger.warning(
            "SECRET_KEY 使用默认值或不足 32 字节，仅限本地开发（prod 会拒绝启动）"
        )
    if settings.MCP_ENABLED:
        logger.warning(
            "已挂载 /mcp 调试台：无鉴权且可执行任意 SQL，只应在本机使用"
        )
    if settings.DEV_SEED_ADMIN:
        logger.warning(
            "开发账号种子已开启：每次启动保证 %s 可登录（prod 会拒绝启动）",
            settings.DEV_ADMIN_USERNAME,
        )
        if settings.DEV_ADMIN_PASSWORD in ("12345", "123456", "password"):
            logger.warning(
                "DEV_ADMIN_PASSWORD 是弱口令 %s，仅限本地开发",
                settings.DEV_ADMIN_PASSWORD,
            )
