from datetime import datetime

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    """会员套餐卡。价格已由后端换算成元，前端不再处理分。"""

    code: str = Field(description="套餐代码：pro_monthly / pro_lifetime")
    name: str
    price: float = Field(description="售价，单位：元")
    original_price: float | None = Field(
        default=None, description="划线价，null 表示不展示"
    )
    period: str = Field(description="monthly / lifetime")
    duration_days: int | None = None
    highlights: list[str] = []
    limits: dict = Field(default_factory=dict, description="权益上限，null = 不限")


class SubscriptionOut(BaseModel):
    """当前订阅摘要。免费用户返回 plan_code=free + is_active=false。"""

    plan_code: str = Field(description="free / pro_monthly / pro_lifetime")
    plan_name: str
    is_active: bool
    source: str | None = Field(default=None, description="monthly / lifetime / trial")
    started_at: datetime | None = None
    expires_at: datetime | None = Field(default=None, description="永久会员为 null")


class QuotaItem(BaseModel):
    """单项额度：上限为 null 表示不限。"""

    key: str
    used: int
    limit: int | None = None
    mode: str = Field(description="ok / degraded / blocked")


class QuotaOut(BaseModel):
    """会员中心与各业务页共用的额度快照。

    `mode` 是全站的粗粒度开关：任何一项 degraded 就降级展示。
    """

    plan_code: str
    is_active: bool
    mode: str = Field(description="ok / degraded / blocked")
    limits: dict = Field(default_factory=dict)
    items: list[QuotaItem] = []
