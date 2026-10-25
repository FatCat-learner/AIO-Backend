"""动作库接口。

读路径全部公开（未登录也能浏览「探索动作库」，登录后才有收藏/常用度语义），
写路径（收藏）需要登录。

媒体一律走 URL：`/static/exercises/gifs/<id>.gif`、`/static/exercises/thumbs/<id>.jpg`。
只把 URL 给客户端、不打进小程序包——小程序主包 2 MB，装不下 123 MB 动图。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user, get_current_user_optional
from core.database import get_db
from core.responses import success_response
from models.exercise import Exercise, UserExerciseFavorite
from models.users import User
from schemas.base import IResponse
from schemas.exercise import (
    ExerciseBrief,
    ExerciseDetail,
    ExerciseFavoriteOut,
    ExerciseListOut,
)

router = APIRouter()

MEDIA_BASE = "/static/exercises"
SORT_FIELDS = {
    "default": (Exercise.use_count.desc(), Exercise.id.asc()),
    "name": (Exercise.zh_name.asc(), Exercise.id.asc()),
    "popular": (Exercise.use_count.desc(), Exercise.id.asc()),
    "new": (Exercise.id.desc(),),
}


def _brief(ex: Exercise) -> dict:
    return {
        "id": ex.id,
        "zh_name": ex.zh_name,
        "en_name": ex.en_name,
        "category": ex.category,
        "body_part": ex.body_part,
        "equipment": ex.equipment,
        "primary_tags": ex.primary_tags,
        "secondary_tags": ex.secondary_tags,
        "usage_tags": ex.usage_tags,
        "gif": f"{MEDIA_BASE}/gifs/{ex.id}.gif",
        "thumb": f"{MEDIA_BASE}/thumbs/{ex.id}.jpg",
    }


@router.get(
    "",
    response_model=IResponse[ExerciseListOut],
    summary="动作库列表（按部位 / 器械 / 肌群 / 关键词筛选）",
)
async def list_exercises(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[
        str | None, Query(max_length=64, description="搜中文名或英文名")
    ] = None,
    body_part: Annotated[str | None, Query(description="部位一级，如 背")] = None,
    equipment: Annotated[str | None, Query(description="器械，如 杠铃")] = None,
    category: Annotated[str | None, Query(description="力量 / 有氧")] = None,
    muscle: Annotated[
        str | None, Query(description="肌群标签，支持一级如 back 或二级如 back.lat")
    ] = None,
    favorite_user: Annotated[bool, Query(description="只看当前用户收藏")] = False,
    sort: Annotated[str, Query(description="default/popular/name/new")] = "default",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
):
    stmt = select(Exercise).where(Exercise.is_active.is_(True))
    count_stmt = (
        select(func.count()).select_from(Exercise).where(Exercise.is_active.is_(True))
    )

    def where(clause):
        nonlocal stmt, count_stmt
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)

    if q:
        like = f"%{q.strip()}%"
        where(or_(Exercise.zh_name.like(like), Exercise.en_name.like(like)))
    if body_part:
        where(Exercise.body_part == body_part)
    if equipment:
        where(Exercise.equipment == equipment)
    if category:
        where(Exercise.category == category)
    if muscle:
        # 一级标签用它当二级标签的前缀（back 命中 back / back.lat / back.trap-upper）
        like = f"%{muscle}%"
        where(
            or_(
                Exercise.primary_tags.like(like),
                Exercise.secondary_tags.like(like),
            )
        )
    if favorite_user:
        if current_user is None:
            raise HTTPException(status_code=401, detail="收藏筛选需要登录")
        sub = select(UserExerciseFavorite.exercise_id).where(
            UserExerciseFavorite.user_id == current_user.id
        )
        where(Exercise.id.in_(sub))

    total = (await db.execute(count_stmt)).scalar_one()
    order = SORT_FIELDS.get(sort, SORT_FIELDS["default"])
    result = await db.execute(stmt.order_by(*order).limit(limit).offset(offset))
    rows = result.scalars().all()

    version = f"{total}-{offset}-{limit}"
    return success_response(
        ExerciseListOut(
            total=total,
            items=[ExerciseBrief(**_brief(r)) for r in rows],
            version=version,
        ),
        message=f"共 {total} 个动作",
    )


@router.get(
    "/filters",
    response_model=IResponse[dict],
    summary="筛选项（部位 / 器械 / 类别 的分组计数）",
)
async def list_filters(db: Annotated[AsyncSession, Depends(get_db)]):
    async def group(col):
        rows = await db.execute(
            select(col, func.count())
            .where(Exercise.is_active.is_(True))
            .group_by(col)
            .order_by(func.count().desc())
        )
        return [{"value": v, "count": c} for v, c in rows.all()]

    return success_response(
        {
            "body_part": await group(Exercise.body_part),
            "equipment": await group(Exercise.equipment),
            "category": await group(Exercise.category),
        }
    )


@router.get(
    "/{exercise_id}",
    response_model=IResponse[ExerciseDetail],
    summary="动作详情（含中文说明与分步要点）",
)
async def get_exercise(exercise_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(Exercise, exercise_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="动作不存在")
    data = dict(ExerciseDetail(**_brief(row)).model_dump())
    data.update(
        instructions=row.instructions, steps=row.steps, attribution=row.attribution
    )
    return success_response(ExerciseDetail(**data))


@router.post(
    "/{exercise_id}/favorite",
    response_model=IResponse[ExerciseFavoriteOut],
    summary="收藏 / 取消收藏（幂等切换）",
)
async def toggle_favorite(
    exercise_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ex = await db.get(Exercise, exercise_id)
    if ex is None or not ex.is_active:
        raise HTTPException(status_code=404, detail="动作不存在")

    key = {"user_id": current_user.id, "exercise_id": exercise_id}
    existing = await db.get(UserExerciseFavorite, (current_user.id, exercise_id))
    if existing is None:
        db.add(UserExerciseFavorite(**key))
        favorited = True
    else:
        await db.delete(existing)
        favorited = False
    await db.commit()
    return success_response(
        ExerciseFavoriteOut(exercise_id=exercise_id, favorited=favorited),
        message="已收藏" if favorited else "已取消收藏",
    )


@router.post(
    "/{exercise_id}/use",
    response_model=IResponse[dict],
    summary="记录一次选用（训练里加了该动作后调用，驱动「常用动作」排序）",
)
async def mark_used(
    exercise_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    ex = await db.get(Exercise, exercise_id)
    if ex is None or not ex.is_active:
        raise HTTPException(status_code=404, detail="动作不存在")
    ex.use_count = (ex.use_count or 0) + 1
    await db.commit()
    return success_response({"id": ex.id, "use_count": ex.use_count})
