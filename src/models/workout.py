import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_volume: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # §6.11：训练标题（默认「今天 · 力量」这类文案）与完成状态。
    # finished_at 非空 = 这次训练已经收口；duration_sec 由客户端上报，
    # 服务端只存不算（暂停时长、后台驻留都只有客户端知道）。
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 软删除：NULL 表示未删除，有值表示删除时间
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # 前向引用必须带引号：WorkoutSet / WorkoutExercise 在本类之后才定义，
    # 去掉引号会在建类时 NameError（UP037 这里不适用）
    sets: Mapped[list["WorkoutSet"]] = relationship(  # noqa: UP037
        back_populates="session", cascade="all, delete-orphan"
    )
    exercises: Mapped[list["WorkoutExercise"]] = relationship(  # noqa: UP037
        back_populates="session", cascade="all, delete-orphan"
    )


class WorkoutExercise(Base):
    """训练里的动作行（一次训练 = 若干动作卡，每张卡下挂若干组）。

    §6.11 的加动作 / 改动作 / 删动作都作用在这张表上；组通过
    `workout_sets.workout_exercise_id` 挂回来。position 是动作顺序（0 起），
    和组的 set_index 一样由服务端在新增时算，客户端可用 PATCH order 调整。
    """

    __tablename__ = "workout_exercises"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    exercise_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("exercises.id"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 备注（「最后一组力竭」这类）与组间休息秒数
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 超级组名：同一次加动作带 name 时，几条动作共用这个值
    superset_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    session: Mapped[WorkoutSession] = relationship(back_populates="exercises")
    sets: Mapped[list["WorkoutSet"]] = relationship(  # noqa: UP037
        back_populates="workout_exercise", cascade="all, delete-orphan"
    )


class WorkoutSet(Base):
    __tablename__ = "workout_sets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    exercise_id: Mapped[str] = mapped_column(String(36), nullable=False)
    set_index: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpe: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # §6.11：逐组落库。workout_exercise_id 指向动作行（老数据 / 同步推上来的
    # 行没有这个值，只靠 session_id + exercise_id 关联，所以必须可空）。
    workout_exercise_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workout_exercises.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    # 打勾才算进训练容量（Σ 重量×次数，与前端 store/workout 的 volume 同源）
    done: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    # 「每组计时」的用时，客户端上报，服务端只存不推算
    spent_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 普通 / 热身 / 递减
    set_type: Mapped[str | None] = mapped_column(
        String(16), default="normal", nullable=True
    )
    # kg / lb，重量数值按上报单位原样存
    unit: Mapped[str | None] = mapped_column(String(8), default="kg", nullable=True)
    # easy / mid / hard（前端口径；文档里写的是 normal，两种都收）
    difficulty: Mapped[str | None] = mapped_column(String(8), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    session: Mapped[WorkoutSession] = relationship(back_populates="sets")
    workout_exercise: Mapped[WorkoutExercise | None] = relationship(
        back_populates="sets"
    )
