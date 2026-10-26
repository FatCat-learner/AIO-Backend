from sqlalchemy import inspect, text
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


# 异步引擎。SQL 回显跟随 DEBUG（prod 下把 DEBUG 设成 false，避免日志泄露语句与参数）
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)

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


# 追加列清单：create_all 只会建新表，不会给已存在的表补列，而本项目没有 Alembic。
# 新加字段时在这里登记一次，启动时按「缺哪列补哪列」幂等地 ALTER。
# 只登记可空 / 带默认值的列，避免 SQLite 对 ADD COLUMN NOT NULL 的限制。
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "workout_sessions": {
        "title": "VARCHAR(100)",
        "finished_at": "{ts}",
        "duration_sec": "INTEGER",
        # 软删除列：线上 PG 的这两张表是早期建的，模型里有但库里没有，
        # 一查就 500（列不存在），所以一并补上
        "deleted_at": "{ts}",
    },
    "workout_sets": {
        "workout_exercise_id": "VARCHAR(36)",
        "done": "{bool} DEFAULT {false}",
        "spent_sec": "INTEGER",
        "set_type": "VARCHAR(16) DEFAULT 'normal'",
        "unit": "VARCHAR(8) DEFAULT 'kg'",
        "difficulty": "VARCHAR(8)",
        "note": "VARCHAR(500)",
        "deleted_at": "{ts}",
    },
}


async def _add_missing_columns(conn) -> None:
    """给已存在的表补上 `_ADDED_COLUMNS` 里登记的列（幂等）。

    老库（Docker 里的 PostgreSQL、本地 aio_demo.db / test_aio.db）不会因为
    模型加了字段就自动变更，所以启动时用 inspector 比对一次再 ALTER。
    """

    def _existing(sync_conn, table: str) -> set[str]:
        inspector = inspect(sync_conn)
        return {col["name"] for col in inspector.get_columns(table)}

    is_sqlite = conn.dialect.name == "sqlite"
    type_map = {
        "{ts}": "DATETIME" if is_sqlite else "TIMESTAMP WITH TIME ZONE",
        "{bool}": "BOOLEAN",
        "{false}": "0" if is_sqlite else "false",
    }

    for table, columns in _ADDED_COLUMNS.items():
        existing = await conn.run_sync(_existing, table)
        if not existing:
            # 表还没建（create_all 之前就调用的场景），交给 create_all
            continue
        for name, ddl in columns.items():
            if name in existing:
                continue
            resolved = ddl
            for key, value in type_map.items():
                resolved = resolved.replace(key, value)
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {name} {resolved}")
            )


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
        # create_all 之后补列：老库里的 workout_sessions / workout_sets 需要
        await _add_missing_columns(conn)
