from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""

    pass


# 异步引擎。echo=True 会打印 SQL，调试时打开
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Session 工厂。expire_on_commit=False 避免 commit 后访问属性报错
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI 依赖：每个请求一个数据库会话，请求结束自动关闭"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """应用启动时建表。
    PostgreSQL 下先启用扩展，SQLite 下跳过"""
    async with engine.begin() as conn:
        # 只有 PostgreSQL 支持 CREATE EXTENSION
        if settings.DATABASE_URL.startswith("postgresql"):
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            if settings.ENABLE_VECTOR:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
