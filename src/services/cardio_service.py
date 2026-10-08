from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models.cardio import CardioSession

IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")


async def save_route(
    db: AsyncSession,
    session_id: str,
    geojson_str: str,
) -> None:
    """写入轨迹。

    所有数据库：写 geojson 文本
    PostgreSQL：额外把 GeoJSON 转成几何写入 route_geom
    """
    await db.execute(
        update(CardioSession)
        .where(CardioSession.id == session_id)
        .values(geojson=geojson_str)
    )

    if IS_POSTGRES:
        await db.execute(
            update(CardioSession)
            .where(CardioSession.id == session_id)
            .values(route_geom=func.ST_GeomFromGeoJSON(geojson_str))
        )


async def read_route(
    db: AsyncSession,
    session_id: str,
) -> str | None:
    """读取轨迹 GeoJSON。

    PostgreSQL：从几何列转回 GeoJSON
    其他数据库：直接读 geojson 文本
    """
    if IS_POSTGRES:
        stmt = select(func.ST_AsGeoJSON(CardioSession.route_geom)).where(
            CardioSession.id == session_id
        )
    else:
        stmt = select(CardioSession.geojson).where(CardioSession.id == session_id)

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def query_nearby(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_m: float,
) -> list[CardioSession]:
    """查找经过某点附近的轨迹。

    PostgreSQL：用 PostGIS 的 ST_DWithin
    SQLite：不支持，返回明确提示
    """
    if not IS_POSTGRES:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="空间查询仅在 PostgreSQL + PostGIS 下支持",
        )

    # 把经纬度转成 PostGIS 点，再判断是否在半径内
    point = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)

    stmt = select(CardioSession).where(
        func.ST_DWithin(CardioSession.route_geom, point, radius_m)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
