import json
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


def _split_tags(value: str | None) -> list[str]:
    """数据库里标签是 "/" 拼接的字符串，出参统一拆成数组。"""
    if not value or value == "—":
        return []
    return [t for t in value.split("/") if t]


class ExerciseBrief(BaseModel):
    """列表项：够画一张卡片（动图 + 名字 + 器械 + 肌群 chip）。"""

    id: str
    zh_name: str
    en_name: str
    category: str
    body_part: str
    equipment: str
    primary_tags: list[str] = Field(default_factory=list)
    secondary_tags: list[str] = Field(default_factory=list)
    usage_tags: list[str] = Field(default_factory=list)
    gif: str = ""
    thumb: str = ""

    @field_validator("primary_tags", "secondary_tags", "usage_tags", mode="before")
    @classmethod
    def _tags(cls, v):
        if isinstance(v, str):
            return _split_tags(v)
        return v or []


class ExerciseDetail(ExerciseBrief):
    """详情页：加中文说明与分步要点。"""

    instructions: str = ""
    steps: list[str] = Field(default_factory=list)
    attribution: str = ""

    @field_validator("steps", mode="before")
    @classmethod
    def _steps(cls, v):
        if isinstance(v, str):
            try:
                out = json.loads(v) if v else []
            except json.JSONDecodeError:
                return []
            return out if isinstance(out, list) else []
        return v or []


class ExerciseListOut(BaseModel):
    total: int
    items: Annotated[list[ExerciseBrief], Field(default_factory=list)]
    # 客户端可据此判断本地快照是否需要刷新
    version: str = ""


class ExerciseFavoriteOut(BaseModel):
    exercise_id: str
    favorited: bool
