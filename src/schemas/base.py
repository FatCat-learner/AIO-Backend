from pydantic import BaseModel, Field


class IResponse[T](BaseModel):
    """业务接口统一响应体。

    成功时 code 为实际 HTTP 状态码、status 为 ``"success"``；
    失败时 code 为错误 HTTP 状态码、status 为 ``"error"``。
    data 的具体结构随接口变化，错误响应没有业务数据时为 null。
    """

    code: int | str = Field(description="响应码；当前取实际 HTTP 状态码")
    data: T = Field(description="业务数据；错误响应中无业务数据时为 null")
    message: str = Field(description="供前端展示或记录的响应说明")
    status: int | str = Field(description="响应状态标记；成功为 success，失败为 error")


class PushPayload(BaseModel):
    """WatermelonDB push 请求体"""

    changes: dict
    last_pulled_at: str | None = None
