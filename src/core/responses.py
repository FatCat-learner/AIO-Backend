from fastapi import HTTPException

from schemas.base import IResponse


def success_response[T](
    data: T,
    message: str = "操作成功",
    code: int = 200,
) -> IResponse[T]:
    """构造成功响应；code 使用 HTTP 状态码，status 使用统一的成功标记。"""
    return IResponse(
        code=code,
        data=data,
        message=message,
        status="success",
    )


class BizHTTPException(HTTPException):
    """带机器可读业务原因的 HTTPException。

    统一错误体里只有 message（= detail）给人看；前端要按业务分支处理时（比如
    「账号未注册」要引导去注册，而不是只弹个错），需要一个稳定标识，
    这里用 reason 落到 envelope 的 data 上。
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        reason: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.reason = reason
