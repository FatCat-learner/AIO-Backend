from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user
from core.database import get_db
from models.users import User
from schemas.base import PushPayload
from services import sync_service

router = APIRouter()


@router.get("/pull", summary="WatermelonDB 拉取变更")
async def pull(
    last_pulled_at: str | None = Query(
        None,
        description="上次同步时间戳。首次同步传 0 或不传",
    ),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
):
    # 解析时间戳。0 或空表示首次同步；格式不合法返回 422 而不是 500
    try:
        since = sync_service.parse_timestamp(last_pulled_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    changes, server_time = await sync_service.pull_changes(db, current_user.id, since)

    return {
        "changes": changes,
        "timestamp": server_time.isoformat(),
    }


@router.post("/push", summary="WatermelonDB 推送本地变更")
async def push(
    payload: PushPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    await sync_service.push_changes(db, current_user.id, payload.changes)
    return {"status": "ok"}
