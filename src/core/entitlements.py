"""会员权益与额度。

设计要点（见《会员权益与角色体系规划 V0.6.4》§5）：

1. **降级而不是拒绝**。用完额度返回 `DEGRADED`，业务侧走「精简模式」，
   响应依旧 200；`BLOCKED` 只留给 B 端协作（如教练带学员的名额上限）。
2. **这里只判不写**。`check_quota()` 是纯函数，不查库、不扣次数；
   计数由调用方（业务路由）在事务里处理，避免两处记账打架。
3. **上限是数据不是代码**。数值存 `membership_plans.limits`（JSON），
   调价调量改数据即可；下面的常量只是种子默认值。
"""

from __future__ import annotations

from enum import StrEnum

from models.membership import MembershipPlan, Subscription


class QuotaResult(StrEnum):
    """额度判定结果。响应里用 `data.mode` 透出，前端据此切换展示形态。"""

    OK = "ok"
    # 超额度但仍可用 → 前端显示「精简模式」，不弹窗、不报错
    DEGRADED = "degraded"
    # 不可用，仅用于 B 端协作类硬门槛
    BLOCKED = "blocked"


# ---- 权益键名（写入 membership_plans.limits，前端/业务统一引用） ----
KEY_AI_MODEL = "ai.model"                    # "fast" / "flagship"
KEY_AI_CHAT_MONTHLY = "ai.chat.monthly"      # 每月 AI 对话轮数
KEY_AI_PLAN_DAILY = "ai.plan.daily"          # 每天生成计划次数
KEY_AI_PLAN_COOLDOWN = "ai.plan.cooldown_days"  # 免费侧「每 N 天 1 次」
KEY_LIB_PLANS = "lib.plans"                  # 计划库上限，None = 不限
KEY_LIB_ROUTES = "lib.routes"                # 路书库上限
KEY_LIB_FAVORITES = "lib.favorites"          # 收藏上限
KEY_CARDIO_DEPTH = "cardio.depth_items"      # 有氧深度分析解锁项数（0 / 4）
KEY_DECOR_MEMBER_POOL = "decor.member_pool"  # 是否可装备会员池装饰

# 会员侧 AI 对话的隐性上限，防止脚本刷量；前端显示「不限」，不对外承诺
PRO_AI_CHAT_MONTHLY = 2000

# ---- 种子套餐（与 §6 定价一致：月付 ¥18、永久 ¥298，早鸟 ¥198） ----
PLAN_PRO_MONTHLY = "pro_monthly"
PLAN_PRO_LIFETIME = "pro_lifetime"

FREE_LIMITS: dict = {
    KEY_AI_MODEL: "fast",
    KEY_AI_CHAT_MONTHLY: 60,
    KEY_AI_PLAN_DAILY: 1,
    KEY_AI_PLAN_COOLDOWN: 3,
    KEY_LIB_PLANS: 5,
    KEY_LIB_ROUTES: 8,
    KEY_LIB_FAVORITES: 10,
    KEY_CARDIO_DEPTH: 0,
    KEY_DECOR_MEMBER_POOL: False,
}

PRO_LIMITS: dict = {
    KEY_AI_MODEL: "flagship",
    KEY_AI_CHAT_MONTHLY: PRO_AI_CHAT_MONTHLY,
    KEY_AI_PLAN_DAILY: 5,
    KEY_AI_PLAN_COOLDOWN: 0,
    KEY_LIB_PLANS: None,
    KEY_LIB_ROUTES: None,
    KEY_LIB_FAVORITES: None,
    KEY_CARDIO_DEPTH: 4,
    KEY_DECOR_MEMBER_POOL: True,
}

# 种子数据：启动时幂等写入，改价改量直接改这里
DEFAULT_PLANS: list[dict] = [
    {
        "code": PLAN_PRO_MONTHLY,
        "name": "Pro 月付",
        "price_cents": 1800,
        "original_price_cents": 0,
        "period": "monthly",
        "duration_days": 31,
        "limits": PRO_LIMITS,
        "highlights": [
            "旗舰模型 · 每天 5 次生成计划",
            "计划 / 路书 / 收藏 无上限",
            "2.5D 轨迹 · 高程剖面 · 训练负荷",
            "会员专属装饰 16 件，每月新增",
        ],
        "sort": 0,
    },
    {
        "code": PLAN_PRO_LIFETIME,
        "name": "Pro 永久",
        "price_cents": 19800,
        "original_price_cents": 29800,
        "period": "lifetime",
        "duration_days": None,
        "limits": PRO_LIMITS,
        "highlights": [
            "一次买断，不做续费提醒",
            "含月付全部权益",
            "早鸟价，限前 1000 名",
        ],
        "sort": 1,
    },
]


def limits_for(plan_code: str | None) -> dict:
    """按套餐代码取权益表；未知/空 → 免费侧。"""
    if plan_code in (PLAN_PRO_MONTHLY, PLAN_PRO_LIFETIME):
        return PRO_LIMITS
    return FREE_LIMITS


def is_pro(plan_code: str | None) -> bool:
    return plan_code in (PLAN_PRO_MONTHLY, PLAN_PRO_LIFETIME)


def pick_active_subscription(subs: list[Subscription], now) -> Subscription | None:
    """从用户全部订阅里挑出当前有效的那条。

    永久会员 `expires_at is None`；月付按时间比较。到期不依赖定时任务改状态。
    """
    active = [
        s
        for s in subs
        if s.status != "canceled" and (s.expires_at is None or s.expires_at > now)
    ]
    if not active:
        return None

    # 优先级：永久（expires_at 为 NULL）> 到期更晚的月付
    def _priority(s: Subscription) -> tuple[int, float]:
        if s.expires_at is None:
            return (0, 0.0)
        return (1, -s.expires_at.timestamp())

    active.sort(key=_priority)
    return active[0]


def check_quota(used: int, limit: int | None, *, hard: bool = False) -> QuotaResult:
    """额度判定。只判不写。

    - `limit is None` → 不限，恒 OK
    - 未超 → OK
    - 超出 → 默认 DEGRADED（降级可用）；`hard=True` 才 BLOCKED（仅 B 端协作）
    """
    if limit is None:
        return QuotaResult.OK
    if used < limit:
        return QuotaResult.OK
    return QuotaResult.BLOCKED if hard else QuotaResult.DEGRADED


def plan_view(plan: MembershipPlan) -> dict:
    """套餐的对外形态：分转元、隐藏内部键。"""
    return {
        "code": plan.code,
        "name": plan.name,
        "price": plan.price_cents / 100,
        "original_price": (
            plan.original_price_cents / 100 if plan.original_price_cents else None
        ),
        "period": plan.period,
        "duration_days": plan.duration_days,
        "highlights": plan.highlights or [],
        "limits": plan.limits or {},
    }
