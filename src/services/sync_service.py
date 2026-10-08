from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.workout import WorkoutSession, WorkoutSet

# 所有参与同步的表，键是 WatermelonDB 的表名，值是 SQLAlchemy 模型
SYNC_TABLES = {
    "workout_sessions": WorkoutSession,
    "workout_sets": WorkoutSet,
}


# 每个表暴露给前端的字段
SYNC_FIELDS = {
    "workout_sessions": [
        "id",
        "user_id",
        "start_time",
        "end_time",
        "total_volume",
        "notes",
    ],
    "workout_sets": [
        "id",
        "session_id",
        "exercise_id",
        "set_index",
        "weight_kg",
        "reps",
        "rpe",
        "rest_seconds",
    ],
}


def _to_record(obj, table_name: str) -> dict:
    """把 ORM 对象转成 WatermelonDB 需要的普通字典"""
    record = {}
    for field in SYNC_FIELDS[table_name]:
        value = getattr(obj, field)
        # 时间统一转成 ISO 字符串，前端处理更方便
        if isinstance(value, datetime):
            record[field] = value.isoformat()
        elif value is None:
            record[field] = None
        else:
            record[field] = value
    return record


async def pull_changes(
    db: AsyncSession,
    user_id: str,
    last_pulled_at: datetime | None,
) -> tuple[dict, datetime]:
    """拉取指定用户在此时间之后的变更。

    返回 (changes, server_time)。
    - changes 结构：{ 表名: { created: [], updated: [], deleted: [] } }
    - server_time 是服务器当前时间，前端下次同步时作为 lastPulledAt
    """
    changes: dict = {}
    now = datetime.now(timezone.utc)

    for table_name, model in SYNC_TABLES.items():
        # 只拉当前用户的数据。workout_sets 通过 session_id 关联到用户
        if table_name == "workout_sessions":
            base = select(model).where(model.user_id == user_id)
        else:
            # workout_sets 没有 user_id，用子查询过滤
            sub = select(WorkoutSession.id).where(WorkoutSession.user_id == user_id)
            base = select(model).where(model.session_id.in_(sub))

        result = await db.execute(base)
        all_records = result.scalars().all()

        created, updated, deleted = [], [], []

        for record in all_records:
            # 判断这条记录属于哪种变更类型
            if record.deleted_at is not None:
                # 被软删除。首次同步返回 deleted，增量同步也要返回
                if last_pulled_at is None or record.deleted_at > last_pulled_at:
                    deleted.append(record.id)
            elif last_pulled_at is None or record.created_at > last_pulled_at:
                # 首次同步，或创建时间在 last_pulled_at 之后
                created.append(_to_record(record, table_name))
            elif record.updated_at > last_pulled_at:
                # 更新时间在 last_pulled_at 之后
                updated.append(_to_record(record, table_name))

        changes[table_name] = {
            "created": created,
            "updated": updated,
            "deleted": deleted,
        }

    return changes, now


async def push_changes(
    db: AsyncSession,
    user_id: str,
    changes: dict,
) -> None:
    """接收前端推送的变更，写入数据库。

    冲突策略：以服务端 updated_at 为准。
    如果服务端记录的 updated_at 比前端新，说明服务端已被修改，跳过这次写入。
    前端应该在下次 pull 时拿到服务端版本。
    """
    now = datetime.now(timezone.utc)

    for table_name, table_changes in changes.items():
        if table_name not in SYNC_TABLES:
            # 未知表名，跳过
            continue

        model = SYNC_TABLES[table_name]

        # 处理新增
        for record in table_changes.get("created", []):
            # 检查是否已存在（可能前端重复推送）
            existing = await db.get(model, record["id"])
            if existing:
                continue

            # 只保留模型里真实存在的字段
            data = {k: v for k, v in record.items() if k in SYNC_FIELDS[table_name]}
            data["user_id"] = user_id  # 强制归属当前用户
            db.add(model(**data))

        # 处理更新
        for record in table_changes.get("updated", []):
            existing = await db.get(model, record["id"])
            if not existing:
                continue
            # 只允许更新自己的数据
            if table_name == "workout_sessions" and existing.user_id != user_id:
                continue

            # 冲突检查：如果服务端已更新，跳过
            incoming_updated = record.get("updated_at")
            if incoming_updated and existing.updated_at:
                incoming_dt = datetime.fromisoformat(incoming_updated)
                if existing.updated_at > incoming_dt:
                    continue

            for field in SYNC_FIELDS[table_name]:
                if field in record and field != "id":
                    setattr(existing, field, record[field])

        # 处理删除（软删除）
        for record_id in table_changes.get("deleted", []):
            existing = await db.get(model, record_id)
            if not existing:
                continue
            if table_name == "workout_sessions" and existing.user_id != user_id:
                continue
            existing.deleted_at = now

    await db.commit()
