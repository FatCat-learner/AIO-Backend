import json
import logging
from pathlib import Path

from sqlalchemy import func, select

from core.config import settings
from core.database import AsyncSessionLocal
from core.entitlements import DEFAULT_PLANS
from core.security import hash_password, verify_password
from models.exercise import Exercise
from models.membership import MembershipPlan
from models.users import User

logger = logging.getLogger(__name__)

# src/core/seed.py → 上三级是项目根 aio-backend/
SEED_EXERCISES = Path(__file__).resolve().parents[2] / "data" / "exercises.seed.json"


def _join_tags(value: object) -> str:
    """种子 json 里标签是数组，落库按模型约定用 "/" 拼成一列。"""
    if isinstance(value, list):
        return "/".join(str(v) for v in value)
    return value if isinstance(value, str) else ""


async def ensure_exercises() -> None:
    """幂等导入动作库（1267 条：力量 1236 + 有氧 31）。

    只在表空时灌。动作 id 是被 workout_sets.exercise_id 引用的业务主键，
    已有记录一律不覆盖——改中文名走后台/迁移，不靠重启。
    """
    if not SEED_EXERCISES.exists():
        logger.warning("动作库种子文件不存在，跳过导入：%s", SEED_EXERCISES)
        return

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(func.count()).select_from(Exercise))
        ).scalar_one()
        if existing:
            logger.debug("动作库已有 %d 条，跳过导入", existing)
            return

        rows = json.loads(SEED_EXERCISES.read_text(encoding="utf-8"))
        db.add_all(
            [
                Exercise(
                    id=row["id"],
                    zh_name=row["zh_name"],
                    en_name=row["en_name"],
                    category=row["category"],
                    body_part=row["body_part"],
                    equipment=row["equipment"],
                    primary_tags=_join_tags(row.get("primary_tags")),
                    secondary_tags=_join_tags(row.get("secondary_tags")),
                    usage_tags=_join_tags(row.get("usage_tags")),
                    instructions=row.get("instructions") or "",
                    # steps 按模型约定存 JSON 数组字符串，出参时 schema 层再拆开
                    steps=json.dumps(row.get("steps") or [], ensure_ascii=False),
                    media_id=row.get("media_id") or "",
                    attribution=row.get("attribution") or "",
                    use_count=0,
                    is_active=True,
                )
                for row in rows
            ]
        )
        await db.commit()
        cardio = sum(1 for row in rows if row.get("category") == "有氧")
        logger.info(
            "动作库已导入 %d 条（力量 %d / 有氧 %d）",
            len(rows),
            len(rows) - cardio,
            cardio,
        )


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
