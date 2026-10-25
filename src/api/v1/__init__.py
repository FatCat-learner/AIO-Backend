from fastapi import APIRouter

from .auth import auth_router
from .cardio import cardio_router
from .exercises import exercises_router
from .health import health_router
from .membership import membership_router
from .sync import sync_router
from .users import users_router
from .workouts import workouts_router

v1_router = APIRouter()

# 每个子模块在这里统一设置 prefix 和 tags
v1_router.include_router(auth_router, prefix="/auth", tags=["用户认证"])
v1_router.include_router(cardio_router, prefix="/cardio", tags=["有氧运动"])
v1_router.include_router(exercises_router, prefix="/exercises", tags=["动作库"])
v1_router.include_router(health_router, prefix="/health", tags=["学习测试"])
v1_router.include_router(membership_router, prefix="/membership", tags=["会员与权益"])
v1_router.include_router(sync_router, prefix="/sync", tags=["数据同步"])
v1_router.include_router(users_router, prefix="/users", tags=["用户管理"])
v1_router.include_router(workouts_router, prefix="/workouts", tags=["训练记录"])

__all__ = ["v1_router"]
