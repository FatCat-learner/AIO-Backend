"""组级写接口（`/api/workout-sets/{set_id}`）。

只拿到 `set_id`，所以归属校验必须走两级：set → session → user，
再看组挂的 workout_exercise 是否还在同一次训练里（见 `common.get_owned_set`）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user
from core.database import get_db
from core.responses import success_response
from models.users import User
from schemas.base import IResponse
from schemas.workout import WorkoutSetUpdate, WorkoutSetUpdatedOut

from .common import get_owned_set, now_utc, set_out

router = APIRouter()


@router.patch(
    "/{set_id}",
    response_model=IResponse[WorkoutSetUpdatedOut],
    summary="改组（重量 / 次数 / 难度 / 打勾 / 用时 / 类型）",
)
async def update_workout_set(
    set_id: str,
    body: WorkoutSetUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    row, _session = await get_owned_set(db, set_id, current_user.id)

    # model_fields_set 区分「没传」与「显式传 null / false」，只改传了的字段
    fields = body.model_fields_set
    if "weight" in fields and body.weight is not None:
        row.weight_kg = body.weight
    if "reps" in fields and body.reps is not None:
        row.reps = body.reps
    if "unit" in fields and body.unit is not None:
        row.unit = body.unit
    if "difficulty" in fields and body.difficulty is not None:
        row.difficulty = body.difficulty
    if "done" in fields and body.done is not None:
        row.done = body.done
    if "spent_sec" in fields and body.spent_sec is not None:
        row.spent_sec = body.spent_sec
    if "set_type" in fields and body.set_type is not None:
        row.set_type = body.set_type
    if "note" in fields and body.note is not None:
        row.note = body.note

    await db.commit()
    await db.refresh(row)
    return success_response(
        WorkoutSetUpdatedOut(ok=True, set=set_out(row)),
        message="已保存",
    )


@router.delete(
    "/{set_id}",
    response_model=IResponse[dict],
    summary="删组（软删除）",
)
async def delete_workout_set(
    set_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    row, _session = await get_owned_set(db, set_id, current_user.id)
    row.deleted_at = now_utc()
    await db.commit()
    return success_response({"ok": True}, message="已删除该组")
