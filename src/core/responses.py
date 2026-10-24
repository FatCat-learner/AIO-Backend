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
