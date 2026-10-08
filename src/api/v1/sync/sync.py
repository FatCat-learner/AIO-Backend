from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
    # 解析时间戳。0 或空表示首次同步
    since = None
    if last_pulled_at and last_pulled_at not in ("0", ""):
        since = datetime.fromisoformat(last_pulled_at)

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
