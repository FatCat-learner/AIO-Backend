import logging

from sqlalchemy import select

from core.config import settings
from core.database import AsyncSessionLocal
from core.entitlements import DEFAULT_PLANS
from core.security import hash_password, verify_password
from models.membership import MembershipPlan
from models.users import User

logger = logging.getLogger(__name__)


async def ensure_dev_account() -> None:
    """开发便利账号：每次启动保证 DEV_ADMIN_USERNAME / DEV_ADMIN_PASSWORD 能登录。

    - 账号不存在 → 建号
    - 账号存在但密码不是配置值、或被禁用 → 重置回来

    这样本地开发随时能用一个固定账号进后台，不用记注册过哪些号。
    上线前把 .env 里的 DEV_SEED_ADMIN 设为 false（默认 true）。
    """

    if not settings.DEV_SEED_ADMIN:
        return

    username = settings.DEV_ADMIN_USERNAME
    password = settings.DEV_ADMIN_PASSWORD

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None:
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    nickname="管理员",
                )
            )
            await db.commit()
            logger.info("开发账号已创建：%s", username)
            return

        changed = False
        if not user.is_active:
            user.is_active = True
            changed = True
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            changed = True

        if changed:
            db.add(user)
            await db.commit()
            logger.info("开发账号已重置为配置口令：%s", username)


async def ensure_membership_plans() -> None:
    """幂等写入会员套餐（§6 定价：月付 ¥18 / 永久 ¥298 早鸟 ¥198）。

    改价改量只改 core/entitlements.py 的 DEFAULT_PLANS，重启即同步；
    已存在则更新价格与权益，不重建行，历史订阅引用不受影响。
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MembershipPlan))
        existing = {p.code: p for p in result.scalars().all()}

        changed = 0
        for spec in DEFAULT_PLANS:
            plan = existing.get(spec["code"])
            if plan is None:
                db.add(MembershipPlan(**spec))
                changed += 1
                continue

            for field, value in spec.items():
                if getattr(plan, field) != value:
                    setattr(plan, field, value)
                    changed += 1

        if changed:
            await db.commit()
            logger.info("会员套餐已同步（%d 处变更）", changed)
