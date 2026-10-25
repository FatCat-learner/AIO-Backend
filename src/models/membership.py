import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class MembershipPlan(Base):
    """会员套餐。

    只有两张卡：月付（自动续费）与永久（一次性买断）。
    价格一律存「分」，避免浮点误差；展示时再除以 100。
    """

    __tablename__ = "membership_plans"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # 稳定代码，前端与权益判定都用它，不随改价变化
    code: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    # 展示名，如「Pro 月付」「Pro 永久」
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 售价，单位：分
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 划线价（早鸟结束后的原价），0 表示不展示
    original_price_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # monthly / lifetime；monthly 才有 duration_days
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 权益上限。键名见 core/entitlements.py，值 int / str / bool / null(=不限)
    limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # 卖点文案，前端直接渲染，避免文案散落在代码里
    highlights: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # 是否在售；下架不删行，历史订阅仍可解析
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 排序，数字小的在前（月付在前、永久在后）
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Subscription(Base):
    """用户订阅。

    一个用户可以有多条历史订阅，权益判定只看「当前有效」那一条：
    `expires_at IS NULL`（永久）或 `expires_at > now()`。
    到期不需要定时任务改状态，读路径直接按时间比较。
    """

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("membership_plans.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    # 冗余存一份套餐代码，历史订阅在套餐改代码后仍能解析
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    # trial / active / canceled —— 到期不改状态，只靠 expires_at 判断
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # monthly / lifetime / trial，用于区分「付费」与「试用」
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # 永久会员为 NULL
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
