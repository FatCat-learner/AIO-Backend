from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.base import get_current_user
from core import entitlements as ent
from core.database import get_db
from core.responses import success_response
from models.membership import MembershipPlan, Subscription
from models.users import User
from schemas.base import IResponse
from schemas.membership import PlanOut, QuotaItem, QuotaOut, SubscriptionOut

router = APIRouter()

# 会员中心要展示的额度项。顺序即展示顺序。
# 注意：`cardio.depth_items` 这类「解锁几项功能」的权益不进这里——
# 它没有「已用/上限」语义，免费侧值是 0，放进额度会让人人一进来就 degraded。
QUOTA_KEYS: list[str] = [
    ent.KEY_AI_CHAT_MONTHLY,
    ent.KEY_AI_PLAN_DAILY,
    ent.KEY_LIB_PLANS,
    ent.KEY_LIB_ROUTES,
    ent.KEY_LIB_FAVORITES,
]


async def _active_subscription(db: AsyncSession, user_id: str) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    return ent.pick_active_subscription(
        list(result.scalars().all()), datetime.now(UTC)
    )


@router.get(
    "/plan",
    response_model=IResponse[list[PlanOut]],
    summary="会员套餐列表（公开）",
)
async def list_plans(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(MembershipPlan)
        .where(MembershipPlan.is_active.is_(True))
        .order_by(MembershipPlan.sort, MembershipPlan.created_at)
    )
    plans = [ent.plan_view(p) for p in result.scalars().all()]
    return success_response([PlanOut(**p) for p in plans])


@router.get(
    "/me",
    response_model=IResponse[SubscriptionOut],
    summary="我的会员状态",
)
async def read_my_subscription(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sub = await _active_subscription(db, current_user.id)
    if sub is None:
        return success_response(
            SubscriptionOut(plan_code="free", plan_name="免费", is_active=False)
        )

    plan = await db.get(MembershipPlan, sub.plan_id)
    return success_response(
        SubscriptionOut(
            plan_code=sub.plan_code,
            plan_name=plan.name if plan else sub.plan_code,
            is_active=True,
            source=sub.source,
            started_at=sub.started_at,
            expires_at=sub.expires_at,
        )
    )


@router.get(
    "/quota",
    response_model=IResponse[QuotaOut],
    summary="额度快照（会员中心 / 各业务页共用）",
)
async def read_quota(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sub = await _active_subscription(db, current_user.id)
    plan_code = sub.plan_code if sub else "free"
    limits = ent.limits_for(plan_code)

    # TODO(P2)：usage 目前恒为 0，等 quota_usage 记账表落地后改为真实计数。
    # 这里保持「判逻辑不变、只是 used 变了」的结构，业务侧不用跟着改。
    items: list[QuotaItem] = []
    worst = ent.QuotaResult.OK
    for key in QUOTA_KEYS:
        limit = limits.get(key)
        used = 0
        mode = ent.check_quota(used, limit)
        if mode is ent.QuotaResult.BLOCKED:
            worst = ent.QuotaResult.BLOCKED
        elif mode is ent.QuotaResult.DEGRADED and worst is ent.QuotaResult.OK:
            worst = ent.QuotaResult.DEGRADED
        items.append(QuotaItem(key=key, used=used, limit=limit, mode=mode.value))

    return success_response(
        QuotaOut(
            plan_code=plan_code,
            is_active=sub is not None,
            mode=worst.value,
            limits=limits,
            items=items,
        )
    )
