from fastapi import APIRouter

from core.config import settings
from schemas.healths import HealthOut

router = APIRouter()


@router.get("", response_model=HealthOut, summary="健康检查")
async def health():
    """用于探活、负载均衡检查。最终路径 /api/health"""
    return HealthOut(status="ok", app=settings.APP_NAME, version="0.1.0")
