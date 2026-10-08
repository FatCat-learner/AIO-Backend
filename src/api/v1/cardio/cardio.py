from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user
from core.database import get_db
from models.cardio import CardioSession
from models.users import User
from schemas.cardio import CardioCreate, CardioOut
from services import cardio_service

router = APIRouter()


@router.post("", response_model=CardioOut, summary="创建有氧记录")
async def create_cardio(
    payload: CardioCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    # 1. 创建记录，先不含轨迹
    session = CardioSession(
        user_id=current_user.id,
        type=payload.type,
        start_time=payload.start_time,
        end_time=payload.end_time,
        distance_m=payload.distance_m,
        duration_s=payload.duration_s,
        avg_hr=payload.avg_hr,
    )
    db.add(session)
    await db.flush()  # 拿到 ID，但未提交

    # 2. 如果有轨迹，交给服务层写入
    if payload.geojson:
        await cardio_service.save_route(db, session.id, payload.geojson)

    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}/geojson", summary="获取轨迹 GeoJSON")
async def get_route_geojson(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    # 校验记录归属
    result = await db.execute(
        select(CardioSession).where(
            CardioSession.id == session_id,
            CardioSession.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="记录不存在")

    # 服务层负责从正确的列读取
    geojson = await cardio_service.read_route(db, session_id)

    return {"id": session_id, "geojson": geojson}


@router.get("/nearby", summary="查找经过附近的轨迹")
async def nearby(
    lat: float,
    lng: float,
    radius_m: float = 500,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
):
    return await cardio_service.query_nearby(db, lat, lng, radius_m)
