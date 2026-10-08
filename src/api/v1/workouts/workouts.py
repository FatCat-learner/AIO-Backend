from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user
from core.database import get_db
from models.users import User
from models.workout import WorkoutSession

router = APIRouter()


@router.post("", summary="创建训练记录（Demo 简化版）")
async def create_workout(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    session = WorkoutSession(
        user_id=current_user.id,
        start_time=datetime.now(timezone.utc),
        total_volume=0,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"id": session.id, "user_id": session.user_id}


@router.get("", summary="列出当前用户的训练记录")
async def list_workouts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(WorkoutSession).where(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.deleted_at.is_(None),  # 排除已删除
        )
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "total_volume": float(s.total_volume or 0),
        }
        for s in sessions
    ]


@router.delete("/{session_id}", summary="删除训练记录")
async def delete_workout(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(
        select(WorkoutSession).where(
            WorkoutSession.id == session_id,
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.deleted_at.is_(None),  # 不能重复删
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="记录不存在")

    session.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "deleted"}
