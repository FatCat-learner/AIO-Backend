import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class User(Base):
    """用户表。字段最小化：只放认证 + 基础资料"""

    __tablename__ = "users"

    # UUID 主键，字符串存储，迁移到 PostgreSQL 时无需改代码
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # 登录名，唯一索引
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    # 密码哈希，绝不存明文
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 昵称，注册时可空，默认用 username
    nickname: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # 是否启用，预留禁用用户
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # 更新时间。同步接口靠它做增量拉取
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
