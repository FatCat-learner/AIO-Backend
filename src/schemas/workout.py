"""训练流程（§6.11）的请求 / 响应模型。

口径统一写在这里，路由只做校验与落库：
- 容量 = Σ(重量 × 次数)，只算 `done=true` 的组（与前端 store/workout 的 volume 同源）
- `spent_sec` 由客户端上报，服务端只存不算
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

# 组类型：普通 / 热身 / 递减（前端 set_type）
SetType = Literal["normal", "warmup", "dropset"]
# 组难度：前端 store/workout 的口径是 easy | mid | hard，
# 技术文档 §6.11 写的是 easy | normal | hard，两种都收，原样落库。
SetDifficulty = Literal["easy", "mid", "normal", "hard"]
WeightUnit = Literal["kg", "lb"]


class LastSet(BaseModel):
    """「上次重量 / 次数」——组行回填与个人最佳都用它。"""

    weight: float = 0
    reps: int = 0
    date: str | None = None


class WorkoutExerciseItem(BaseModel):
    """动作项（加动作 / 改动作的返回，前端直接渲染一张动作卡）。"""

    workout_exercise_id: str
    exercise_id: str
    name: str
    thumb: str
    position: int = 0
    note: str = ""
    rest_seconds: int | None = None
    superset_name: str | None = None
    last: LastSet | None = None


class WorkoutExerciseListOut(BaseModel):
    items: list[WorkoutExerciseItem] = Field(default_factory=list)


class WorkoutExerciseAdd(BaseModel):
    """加动作。

    - 普通批量：`{ exercise_ids: ["0001", "0002"] }`
    - 超级组：多带一个 `name`，这批动作共用该组名
    - `use_prev_values`：文档里用于回填上次重量/次数；当前实现一律把 `last`
      带回（同一批只查一次库），所以开不开都不影响返回。
    """

    exercise_ids: Annotated[list[str], Field(min_length=1, max_length=20)]
    name: str | None = Field(None, max_length=64, description="超级组名")
    use_prev_values: bool = False


class WorkoutExerciseUpdate(BaseModel):
    """改动作：备注 / 组间休息 / 顺序，只改传了的字段。"""

    note: str | None = Field(None, max_length=500)
    rest_seconds: int | None = Field(None, ge=0, le=3600)
    order: int | None = Field(None, ge=0)


class WorkoutSetCreate(BaseModel):
    """加一组（逐组落库，不整份重传）。"""

    workout_exercise_id: str
    weight: Annotated[float, Field(ge=0, le=1000)] = 0
    reps: Annotated[int, Field(ge=0, le=1000)] = 0
    unit: WeightUnit = "kg"
    difficulty: SetDifficulty | None = None
    done: bool = False
    spent_sec: int | None = Field(None, ge=0, le=86400)
    set_type: SetType = "normal"
    note: str | None = Field(None, max_length=500)


class WorkoutSetUpdate(BaseModel):
    """改组：全部可选，但至少要传一项，避免空 PATCH 白改一次 updated_at。"""

    weight: Annotated[float | None, Field(ge=0, le=1000)] = None
    reps: Annotated[int | None, Field(ge=0, le=1000)] = None
    unit: WeightUnit | None = None
    difficulty: SetDifficulty | None = None
    done: bool | None = None
    spent_sec: int | None = Field(None, ge=0, le=86400)
    set_type: SetType | None = None
    note: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("至少传一个可改字段")
        return self


class WorkoutSetOut(BaseModel):
    set_id: str
    workout_exercise_id: str | None = None
    exercise_id: str
    set_index: int
    weight: float = 0
    reps: int = 0
    unit: str = "kg"
    difficulty: str | None = None
    done: bool = False
    spent_sec: int | None = None
    set_type: str = "normal"
    note: str | None = None


class WorkoutSetUpdatedOut(BaseModel):
    ok: bool = True
    set: WorkoutSetOut


class WorkoutFinishIn(BaseModel):
    """完成训练：duration 由客户端算好再传，title / note 可空。"""

    title: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=500)
    duration_sec: Annotated[int, Field(ge=0, le=604800)]


class FinishedSession(BaseModel):
    id: str
    title: str = ""
    volume: float
    set_count: int
    exercise_count: int
    duration_sec: int
    finished_at: datetime


class WorkoutFinishOut(BaseModel):
    session: FinishedSession


class HistorySet(BaseModel):
    """历史里的一组（够前端画「上次 60kg × 10」）。"""

    weight: float = 0
    reps: int = 0
    set_type: str = "normal"
    done: bool = False


class HistorySession(BaseModel):
    date: str
    session_id: str
    sets: list[HistorySet] = Field(default_factory=list)


class ExerciseHistoryOut(BaseModel):
    exercise_id: str
    name: str = ""
    items: list[HistorySession] = Field(default_factory=list)
    # 最近一次该动作的最重一组（组行回填用）
    last: LastSet | None = None
    # 个人最佳：单组最大重量，并列取次数多者
    pr: LastSet | None = None
    # 该动作练过多少次（用于「第 N 次练」这类文案）
    total: int = 0
