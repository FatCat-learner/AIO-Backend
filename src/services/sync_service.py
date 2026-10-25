from datetime import datetime, timezone

from sqlalchemy import select
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

# 前端推上来需要从 ISO 字符串还原成 datetime 的字段。
# created_at / updated_at / deleted_at 由服务端维护，不接受前端写入。
DATETIME_FIELDS = {
    "workout_sessions": ("start_time", "end_time"),
    "workout_sets": (),
}


def _as_utc(value: datetime | None) -> datetime | None:
    """统一成带 UTC 时区的 datetime。

    SQLite 的 DateTime(timezone=True) 读回来是 naive，而接口传进来的是带时区的
    ISO 串；不统一就无法直接比较（naive 与 aware 相比会抛 TypeError）。
    naive 一律按 UTC 理解：SQLite 的 CURRENT_TIMESTAMP 存的就是 UTC。
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: object) -> datetime | None:
    """把前端推来的时间值统一成带 UTC 时区的 datetime。

    支持 ISO 字符串（含末尾 Z）、秒/毫秒时间戳和 datetime 实例。
    解析不了就抛 ValueError，由路由层转成 4xx，绝不把坏数据静默写进库。
    """
    if value is None or isinstance(value, datetime):
        return _as_utc(value)  # type: ignore[arg-type]
    if isinstance(value, (int, float)):
        # 兼容毫秒时间戳
        seconds = value / 1000 if abs(value) > 1e11 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return _as_utc(datetime.fromisoformat(text))
        except ValueError as exc:
            raise ValueError(f"时间格式无法解析：{value!r}") from exc
    raise ValueError(f"不支持的时间值类型：{type(value).__name__}")


def _normalize_record(record: dict, table_name: str) -> dict:
    """只保留模型里真实存在的字段，并把时间字段还原成 datetime。"""
    data = {
        key: value for key, value in record.items() if key in SYNC_FIELDS[table_name]
    }
    for field in DATETIME_FIELDS.get(table_name, ()):
        if field in data:
            data[field] = _parse_datetime(data[field])
    return data


def _to_record(obj, table_name: str) -> dict:
    """把 ORM 对象转成 WatermelonDB 需要的普通字典"""
    record = {}
    for field in SYNC_FIELDS[table_name]:
        value = getattr(obj, field)
        # 时间统一转成带时区的 ISO 字符串，前端不需要再猜时区
        if isinstance(value, datetime):
            record[field] = _as_utc(value).isoformat()
        else:
            record[field] = value
    return record


def parse_timestamp(value: str | None) -> datetime | None:
    """解析 pull 的 last_pulled_at 查询参数。

    0 或空表示首次同步。注意查询串里的 "+00:00" 有一部分客户端（含
    TestClient）不会做 URL 编码，服务端会把它解码成空格，这里一并还原，
    否则 datetime.fromisoformat 会直接报错。
    """
    if value is None:
        return None
    text = value.strip()
    if text in ("", "0"):
        return None
    return _parse_datetime(text.replace(" ", "+"))


async def _owns_session(    db: AsyncSession,
    session_id: str | None,
    user_id: str,
) -> bool:
    """判断 session 是否属于当前用户。

    workout_sets 没有 user_id 列，只能通过 session 回溯归属，否则可以越权改他人数据。
    """
    if not session_id:
        return False
    session = await db.get(WorkoutSession, session_id)
    return session is not None and session.user_id == user_id


async def _owns_record(
    db: AsyncSession,
    table_name: str,
    record,
    user_id: str,
) -> bool:
    """统一的归属校验入口"""
    if table_name == "workout_sessions":
        return record.user_id == user_id
    return await _owns_session(db, record.session_id, user_id)


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
    since = _as_utc(last_pulled_at)

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
            # 判断这条记录属于哪种变更类型。时间统一成 UTC 再比较，
            # 否则 SQLite 读回的 naive datetime 与传入的 aware datetime 无法比较
            created_at = _as_utc(record.created_at)
            updated_at = _as_utc(record.updated_at)
            deleted_at = _as_utc(record.deleted_at)

            if deleted_at is not None:
                # 被软删除。首次同步返回 deleted，增量同步也要返回
                if since is None or deleted_at > since:
                    deleted.append(record.id)
            elif since is None or created_at > since:
                # 首次同步，或创建时间在 last_pulled_at 之后
                created.append(_to_record(record, table_name))
            elif updated_at > since:
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
            if not record.get("id"):
                continue

            # 检查是否已存在（可能前端重复推送）
            existing = await db.get(model, record["id"])
            if existing:
                continue

            data = _normalize_record(record, table_name)

            if table_name == "workout_sessions":
                data["user_id"] = user_id  # 强制归属当前用户
            else:
                # workout_sets 没有 user_id 列，靠 session 归属校验
                data.pop("user_id", None)
                if not await _owns_session(db, data.get("session_id"), user_id):
                    continue

            db.add(model(**data))

        # 处理更新
        for record in table_changes.get("updated", []):
            existing = await db.get(model, record["id"])
            if not existing:
                continue
            # 只允许更新自己的数据（sets 走 session 归属回溯）
            if not await _owns_record(db, table_name, existing, user_id):
                continue

            # 冲突检查：如果服务端已更新，跳过
            incoming_updated = record.get("updated_at")
            if incoming_updated and existing.updated_at:
                if _as_utc(existing.updated_at) > _parse_datetime(incoming_updated):
                    continue

            # 不允许通过更新改动主键与归属
            incoming = _normalize_record(record, table_name)
            incoming.pop("id", None)
            incoming.pop("user_id", None)
            incoming.pop("session_id", None)

            for field, value in incoming.items():
                setattr(existing, field, value)

        # 处理删除（软删除）
        for record_id in table_changes.get("deleted", []):
            existing = await db.get(model, record_id)
            if not existing:
                continue
            if not await _owns_record(db, table_name, existing, user_id):
                continue
            existing.deleted_at = now

    await db.commit()
