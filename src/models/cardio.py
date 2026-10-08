import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.config import settings
from core.database import Base

# 在模块加载时判断一次，后面所有分支都用它
IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")


class CardioSession(Base):
    """有氧运动记录。

    存储策略：
    - geojson：所有数据库都存，Text 类型，保留完整轨迹
    - route_geom：仅 PostgreSQL 定义，Geometry 类型，用于空间索引和空间查询
    """

    __tablename__ = "cardio_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    # run / ride / walk / hike
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    distance_m: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 通用字段：GeoJSON 字符串，所有数据库都有
    geojson: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # PostgreSQL 下额外定义几何列。
    # 类体内的 if 是合法 Python，SQLAlchemy 声明式映射会扫描类命名空间
    if IS_POSTGRES:
        from geoalchemy2 import Geometry
        from sqlalchemy import Column

        route_geom = Column(
            Geometry(
                geometry_type="LINESTRING",
                srid=4326,
                spatial_index=True,  # 自动创建 GiST 索引
            ),
            nullable=True,
        )
