import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Exercise(Base):
    """动作库（力量 + 有氧共 1267 条，来源 hasaneyldrm/exercises-dataset，中文名与肌群标签人工校对过）。

    主键是数据集自带的 4 位字符串 id（"0001"），不是 UUID：
    workout_sets.exercise_id 存的就是这个值，历史训练记录靠它关联，
    所以这个 id 一旦入库不可变（改中文名只改 zh_name）。
    """

    __tablename__ = "exercises"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    zh_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    en_name: Mapped[str] = mapped_column(String(160), nullable=False)

    # 力量 / 有氧
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # 部位一级（前端左栏）：胸/背/腿/肩/核心/二头/三头/小腿/臀部/前臂/斜方肌/前锯肌/颈部/有氧
    body_part: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # 器械（前端顶部 chip）：杠铃/哑铃/壶铃/绳索/器械/史密斯机/TRX&弹力带/瑜伽球&药球/自重/悍马机/其他
    equipment: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    # 肌群标签用 "/" 拼成一列（如 "abs/abs.oblique"），读取时在 schema 层拆成数组。
    # 不单独建关联表：标签是只读展示维度，前端只做筛选，没有反向查询需求。
    primary_tags: Mapped[str] = mapped_column(String(255), default="")
    secondary_tags: Mapped[str] = mapped_column(String(255), default="")
    usage_tags: Mapped[str] = mapped_column(String(255), default="")

    # 中文动作说明与分步要点（steps 存 JSON 数组字符串）
    instructions: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[str] = mapped_column(Text, default="")

    media_id: Mapped[str] = mapped_column(String(24), default="")
    attribution: Mapped[str] = mapped_column(String(120), default="")

    # 常用度：训练里被选用的次数（seed 时为 0，选中一次 +1）。「常用动作」页按它倒序。
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserExerciseFavorite(Base):
    """用户收藏（探索页收藏夹 / 置顶 chip）。

    用复合主键 (user_id, exercise_id) 表达唯一性，省掉自增 id 与唯一索引。
    """

    __tablename__ = "user_exercise_favorites"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


__all__ = ["Exercise", "UserExerciseFavorite"]
