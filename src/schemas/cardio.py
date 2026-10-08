from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CardioCreate(BaseModel):
    """创建有氧记录请求体"""

    type: str = Field(description="run / ride / walk / hike")
    start_time: datetime
    end_time: datetime | None = None
    distance_m: float | None = None
    duration_s: int | None = None
    avg_hr: int | None = None
    # GeoJSON 字符串，例如：
    # {"type":"LineString","coordinates":[[116.4,39.9],[116.5,40.0]]}
    geojson: str | None = Field(
        default=None,
        description="轨迹 GeoJSON 字符串，可选",
    )


class CardioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: str
    start_time: datetime
    end_time: datetime | None
    distance_m: float | None
    duration_s: int | None
    avg_hr: int | None
