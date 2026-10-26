"""训练记录接口。

- 老 P0 的 CRUD：创建 / 列表 / 删除（整份提交时代的遗留）
- §6.11 训练流程：加动作、改动作、删动作、加组、完成训练（逐组落库）
组级「改组 / 删组」在 `sets.py`（路径前缀 `/api/workout-sets`）。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user
from core.database import get_db
from core.responses import success_response
from models.exercise import Exercise
from models.users import User
from models.workout import WorkoutExercise, WorkoutSession, WorkoutSet
from schemas.base import IResponse
from schemas.workout import (
    FinishedSession,
    WorkoutExerciseAdd,
    WorkoutExerciseItem,
    WorkoutExerciseListOut,
    WorkoutExerciseUpdate,
    WorkoutFinishIn,
    WorkoutFinishOut,
    WorkoutSetCreate,
    WorkoutSetOut,
)

from .common import (
    exercise_item,
    get_owned_workout,
    get_owned_workout_exercise,
    last_sets,
    now_utc,
    set_out,
    volume_of,
)

router = APIRouter()


@router.post(
    "",
    response_model=IResponse[dict],
    summary="创建训练记录（Demo 简化版）",
)
async def create_workout(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    session = WorkoutSession(
        user_id=current_user.id,
        start_time=datetime.now(UTC),
        total_volume=0,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return success_response({"id": session.id, "user_id": session.user_id})


@router.get("", response_model=IResponse[list[dict]], summary="列出当前用户的训练记录")
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
    data = [
        {
            "id": s.id,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "total_volume": float(s.total_volume or 0),
            "title": s.title or "",
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            "duration_sec": s.duration_sec,
        }
        for s in sessions
    ]
    return success_response(data)


@router.post(
    "/{workout_id}/exercises",
    response_model=IResponse[WorkoutExerciseListOut],
    summary="加动作（批量 / 超级组）",
)
async def add_workout_exercises(
    workout_id: str,
    body: WorkoutExerciseAdd,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """第一级校验：workout 属于当前用户；动作必须存在且在架。

    `name` 有值时这批动作共用它（超级组），否则就是普通批量加。
    同一场训练里已存在的动作直接复用，连点 / 断网重试不会多出重复动作卡。
    """
    workout = await get_owned_workout(db, workout_id, current_user.id)

    # 去重但保留入参顺序
    exercise_ids = list(dict.fromkeys(body.exercise_ids))
    found = (
        await db.execute(
            select(Exercise).where(
                Exercise.id.in_(exercise_ids),
                Exercise.is_active.is_(True),
            )
        )
    ).scalars()
    by_id = {ex.id: ex for ex in found}
    missing = [i for i in exercise_ids if i not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"动作不存在：{', '.join(missing)}")

    existing = (
        await db.execute(
            select(WorkoutExercise).where(
                WorkoutExercise.session_id == workout.id,
                WorkoutExercise.deleted_at.is_(None),
            )
        )
    ).scalars()
    existing_by_exercise = {row.exercise_id: row for row in existing}
    next_position = max((row.position for row in existing), default=-1) + 1

    rows: list[WorkoutExercise] = []
    for exercise_id in exercise_ids:
        row = existing_by_exercise.get(exercise_id)
        if row is not None:
            if body.name and row.superset_name != body.name:
                row.superset_name = body.name
            rows.append(row)
            continue
        row = WorkoutExercise(
            session_id=workout.id,
            exercise_id=exercise_id,
            position=next_position,
            superset_name=body.name,
        )
        next_position += 1
        db.add(row)
        existing_by_exercise[exercise_id] = row
        rows.append(row)

    await db.commit()

    lasts = await last_sets(db, current_user.id, exercise_ids)
    items = [
        exercise_item(row, by_id.get(row.exercise_id), lasts.get(row.exercise_id))
        for row in rows
    ]
    return success_response(
        WorkoutExerciseListOut(items=items),
        message=f"已加入 {len(items)} 个动作",
    )


@router.patch(
    "/{workout_id}/exercises/{we_id}",
    response_model=IResponse[WorkoutExerciseItem],
    summary="改动作（备注 / 组间休息 / 顺序）",
)
async def update_workout_exercise(
    workout_id: str,
    we_id: str,
    body: WorkoutExerciseUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """两级校验：workout 是当前用户的，且 we_id 属于这场 workout。"""
    workout = await get_owned_workout(db, workout_id, current_user.id)
    row = await get_owned_workout_exercise(db, workout, we_id)

    if body.note is not None:
        row.note = body.note
    if body.rest_seconds is not None:
        row.rest_seconds = body.rest_seconds
    if body.order is not None:
        row.position = body.order
    await db.commit()

    exercise = await db.get(Exercise, row.exercise_id)
    lasts = await last_sets(db, current_user.id, [row.exercise_id])
    return success_response(
        exercise_item(row, exercise, lasts.get(row.exercise_id)),
        message="已保存",
    )


@router.delete(
    "/{workout_id}/exercises/{we_id}",
    response_model=IResponse[dict],
    summary="删动作（连同该动作下的组一起软删）",
)
async def delete_workout_exercise(
    workout_id: str,
    we_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    workout = await get_owned_workout(db, workout_id, current_user.id)
    row = await get_owned_workout_exercise(db, workout, we_id)

    now = now_utc()
    row.deleted_at = now
    # 组跟着动作一起软删，否则容量 / 历史还会算到已删掉的卡
    await db.execute(
        update(WorkoutSet)
        .where(
            WorkoutSet.workout_exercise_id == row.id,
            WorkoutSet.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    await db.commit()
    return success_response({"ok": True}, message="已删除动作")


@router.post(
    "/{workout_id}/sets",
    response_model=IResponse[WorkoutSetOut],
    summary="加一组（逐组落库）",
)
async def add_workout_set(
    workout_id: str,
    body: WorkoutSetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """两级校验：workout 属于当前用户，且 workout_exercise_id 属于这场 workout。

    `spent_sec` 原样落库（客户端上报），`set_index` 由服务端按当前最大序号 +1。
    """
    workout = await get_owned_workout(db, workout_id, current_user.id)
    we = await get_owned_workout_exercise(db, workout, body.workout_exercise_id)

    max_index = (
        await db.execute(
            select(func.max(WorkoutSet.set_index)).where(
                WorkoutSet.workout_exercise_id == we.id,
                WorkoutSet.deleted_at.is_(None),
            )
        )
    ).scalar()

    row = WorkoutSet(
        session_id=workout.id,
        workout_exercise_id=we.id,
        exercise_id=we.exercise_id,
        set_index=0 if max_index is None else max_index + 1,
        weight_kg=body.weight,
        reps=body.reps,
        done=body.done,
        spent_sec=body.spent_sec,
        set_type=body.set_type,
        unit=body.unit,
        difficulty=body.difficulty,
        note=body.note,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return success_response(set_out(row), message="已加一组")


@router.post(
    "/{workout_id}/finish",
    response_model=IResponse[WorkoutFinishOut],
    summary="完成训练（落 finished_at / 时长 / 容量 / 标题 / 心得）",
)
async def finish_workout(
    workout_id: str,
    body: WorkoutFinishIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """容量在这里算一次并落库，算法与前端 `store/workout` 的 volume 同源。

    重复调用是幂等的：重新按当前组数据算一遍再覆盖，方便断网重试。
    """
    workout = await get_owned_workout(db, workout_id, current_user.id)

    sets = (
        await db.execute(
            select(WorkoutSet).where(
                WorkoutSet.session_id == workout.id,
                WorkoutSet.deleted_at.is_(None),
            )
        )
    ).scalars()
    rows = list(sets)
    done_rows = [row for row in rows if row.done]
    volume = volume_of(rows)
    finished_at = now_utc()

    workout.finished_at = finished_at
    workout.end_time = finished_at
    workout.duration_sec = body.duration_sec
    workout.total_volume = volume
    if body.title is not None:
        workout.title = body.title
    if body.note is not None:
        workout.notes = body.note
    await db.commit()

    return success_response(
        WorkoutFinishOut(
            session=FinishedSession(
                id=workout.id,
                title=workout.title or "",
                volume=volume,
                # 完成量只数打了勾的：组数 = 勾的组，动作数 = 有勾选组的动作
                set_count=len(done_rows),
                exercise_count=len(
                    {row.workout_exercise_id or row.exercise_id for row in done_rows}
                ),
                duration_sec=body.duration_sec,
                finished_at=finished_at,
            )
        ),
        message="训练完成",
    )


@router.delete(
    "/{session_id}",
    response_model=IResponse[dict],
    summary="删除训练记录",
)
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

    session.deleted_at = datetime.now(UTC)
    await db.commit()
    return success_response({"status": "deleted"}, message="删除成功")
