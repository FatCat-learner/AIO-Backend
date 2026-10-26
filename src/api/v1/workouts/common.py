"""训练流程写接口的共用校验与序列化。

越权防护是 §6.11 的第一条硬要求，这里统一成两级：
1. `workout` 必须属于当前用户（`get_owned_workout`）
2. `we_id` / `set_id` 必须属于这个 workout（`get_owned_workout_exercise` /
   `get_owned_set` 里显式比对 session_id）
只校验第一级就是历史踩过的坑（sets 能写进别人的 session）。
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.exercise import Exercise
from models.workout import WorkoutExercise, WorkoutSession, WorkoutSet
from schemas.workout import (
    HistorySet,
    LastSet,
    WorkoutExerciseItem,
    WorkoutSetOut,
)

MEDIA_BASE = "/static/exercises"


def now_utc() -> datetime:
    return datetime.now(UTC)


async def get_owned_workout(
    db: AsyncSession, workout_id: str, user_id: str
) -> WorkoutSession:
    """取当前用户的训练；不存在 / 已删 / 别人的一律 404（不暴露他人 id 是否存在）。"""
    session = await db.get(WorkoutSession, workout_id)
    if session is None or session.deleted_at is not None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="训练记录不存在")
    return session


async def get_owned_workout_exercise(
    db: AsyncSession, session: WorkoutSession, we_id: str
) -> WorkoutExercise:
    """第二级校验：动作行必须挂在这场训练下（同一个人另一场训练也不行）。"""
    row = await db.get(WorkoutExercise, we_id)
    if row is None or row.deleted_at is not None or row.session_id != session.id:
        raise HTTPException(status_code=404, detail="训练动作不存在")
    return row


async def get_owned_set(
    db: AsyncSession, set_id: str, user_id: str
) -> tuple[WorkoutSet, WorkoutSession]:
    """组级写接口只拿到 set_id，必须 set → session → user 两级回溯。

    另外如果这组挂了 workout_exercise_id，还要确认动作行没被删、且和组的
    session 一致——防止「组还活着但动作卡已删」的幽灵数据被改。
    """
    row = await db.get(WorkoutSet, set_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="组不存在")

    session = await db.get(WorkoutSession, row.session_id)
    if session is None or session.deleted_at is not None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="组不存在")

    if row.workout_exercise_id:
        we = await db.get(WorkoutExercise, row.workout_exercise_id)
        if we is None or we.deleted_at is not None or we.session_id != session.id:
            raise HTTPException(status_code=404, detail="组不存在")

    return row, session


def volume_of(sets: Iterable[WorkoutSet]) -> float:
    """Σ 重量 × 次数，只算 `done=true` 的组。

    与前端 `store/workout` 的 `volume` getter 同口径：自重动作 weight=0
    但计次，所以为 0 的组也照样把次数乘进去（结果还是 0）。
    """
    total = sum(
        float(row.weight_kg or 0) * int(row.reps or 0) for row in sets if row.done
    )
    return round(total, 2)


def exercise_item(
    row: WorkoutExercise,
    exercise: Exercise | None,
    last: LastSet | None,
) -> WorkoutExerciseItem:
    return WorkoutExerciseItem(
        workout_exercise_id=row.id,
        exercise_id=row.exercise_id,
        name=exercise.zh_name if exercise else row.exercise_id,
        thumb=f"{MEDIA_BASE}/thumbs/{row.exercise_id}.jpg",
        position=row.position,
        note=row.note or "",
        rest_seconds=row.rest_seconds,
        superset_name=row.superset_name,
        last=last,
    )


def set_out(row: WorkoutSet) -> WorkoutSetOut:
    """组行出参：口径（done / set_type / unit）读空时给默认值。"""
    return WorkoutSetOut(
        set_id=row.id,
        workout_exercise_id=row.workout_exercise_id,
        exercise_id=row.exercise_id,
        set_index=row.set_index,
        weight=float(row.weight_kg or 0),
        reps=int(row.reps or 0),
        unit=row.unit or "kg",
        difficulty=row.difficulty,
        done=bool(row.done),
        spent_sec=row.spent_sec,
        set_type=row.set_type or "normal",
        note=row.note,
    )


def history_set(row: WorkoutSet) -> HistorySet:
    return HistorySet(
        weight=float(row.weight_kg or 0),
        reps=int(row.reps or 0),
        set_type=row.set_type or "normal",
        done=bool(row.done),
    )


async def last_sets(
    db: AsyncSession, user_id: str, exercise_ids: list[str]
) -> dict[str, LastSet]:
    """每个动作「最近一次训练里最重的一组」，一条 SQL 批量取回。

    按 start_time 倒序 + 重量/次数倒序排，第一次出现的那个就是答案；
    只认 done=true 的组（没打勾的组是没做完的草稿行）。
    """
    if not exercise_ids:
        return {}

    stmt = (
        select(
            WorkoutSet.exercise_id,
            WorkoutSet.weight_kg,
            WorkoutSet.reps,
            WorkoutSession.start_time,
        )
        .join(WorkoutSession, WorkoutSession.id == WorkoutSet.session_id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.deleted_at.is_(None),
            WorkoutSet.deleted_at.is_(None),
            WorkoutSet.done.is_(True),
            WorkoutSet.exercise_id.in_(exercise_ids),
        )
        .order_by(
            WorkoutSession.start_time.desc(),
            func.coalesce(WorkoutSet.weight_kg, 0).desc(),
            func.coalesce(WorkoutSet.reps, 0).desc(),
        )
    )

    rows = (await db.execute(stmt)).all()
    result: dict[str, LastSet] = {}
    for exercise_id, weight, reps, start_time in rows:
        if exercise_id in result:
            continue
        result[exercise_id] = LastSet(
            weight=float(weight or 0),
            reps=int(reps or 0),
            date=start_time.date().isoformat() if start_time else None,
        )
    return result
