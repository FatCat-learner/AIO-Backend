import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import api_router
from core.config import settings
from core.database import init_db
from core.mcp import mcp_lifespan, mount_mcp

# 必须导入模型，否则 Base.metadata 里没有表，create_all 建不出来
from models.cardio import CardioSession  # noqa: F401
from models.users import User  # noqa: F401
from models.workout import WorkoutSession, WorkoutSet  # noqa: F401
from schemas.base import IResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时建表，并把 MCP 服务器的会话管理器一起拉起来"""
    await init_db()
    if settings.MCP_ENABLED:
        async with mcp_lifespan():
            yield
    else:
        yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """将 HTTP 错误转换为统一响应，同时保留原有 HTTP 状态码和响应头。"""
    response = IResponse[None](
        code=exc.status_code,
        data=None,
        message=str(exc.detail),
        status="error",
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(response.model_dump()),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """参数校验失败时保留字段级错误详情，便于前端定位并提示用户。"""
    response = IResponse[list[dict]](
        code=422,
        data=exc.errors(),
        message="请求参数校验失败",
        status="error",
    )
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(response.model_dump()),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """兜底未预期异常：服务端记录完整堆栈，客户端只收到通用错误信息。"""
    logger.exception(
        "处理请求时发生未预期异常：%s %s",
        request.method,
        request.url.path,
    )
    response = IResponse[None](
        code=500,
        data=None,
        message="服务器内部错误",
        status="error",
    )
    return JSONResponse(
        status_code=500,
        content=jsonable_encoder(response.model_dump()),
    )


# 所有接口挂 /api前缀
app.include_router(api_router, prefix="/api")

# MCP 依赖注入服务器：端点 /mcp，必须挂在所有业务路由之后，避免抢路由
if settings.MCP_ENABLED:
    mount_mcp(app)
