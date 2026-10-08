from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import api_router
from core.config import settings
from core.database import init_db

# 必须导入模型，否则 Base.metadata 里没有表，create_all 建不出来
from models.cardio import CardioSession  # noqa: F401
from models.users import User  # noqa: F401
from models.workout import WorkoutSession, WorkoutSet  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时建表"""
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# 所有接口挂 /api前缀
app.include_router(api_router, prefix="/api")
