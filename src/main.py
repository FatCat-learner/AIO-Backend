import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import api_router
from core.config import settings, validate_settings
from core.database import init_db
from core.mcp import mcp_lifespan, mount_mcp
from core.seed import ensure_dev_account, ensure_exercises, ensure_membership_plans

# 必须导入模型，否则 Base.metadata 里没有表，create_all 建不出来
from models.cardio import CardioSession  # noqa: F401
from models.exercise import Exercise, UserExerciseFavorite  # noqa: F401
from models.membership import MembershipPlan, Subscription  # noqa: F401
from models.users import User  # noqa: F401
from models.workout import WorkoutExercise, WorkoutSession, WorkoutSet  # noqa: F401
from schemas.base import IResponse

logger = logging.getLogger(__name__)

# 动作库媒体（1267 gif + 1267 缩略图，约 135 MB）。只放本机静态目录、不进 git，
# 小程序那边永远走 URL /static/exercises/...，不打进包里。
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时建表、保证开发账号可登录，并把 MCP 服务器的会话管理器一起拉起来"""
    # 配置体检必须最先跑：prod 下带着默认密钥/调试入口一律不启动
    validate_settings()
    await init_db()
    await ensure_dev_account()
    await ensure_membership_plans()
    await ensure_exercises()
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

# H5 前端（vite dev / 局域网调试）跨域访问：来源从 CORS_ORIGINS 读，默认只放行本机端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """将 HTTP 错误转换为统一响应，同时保留原有 HTTP 状态码和响应头。"""
    # 业务错误可以带 reason（如 account_not_registered），前端据此分支提示
    reason = getattr(exc, "reason", None)
    response = IResponse[dict[str, str] | None](
        code=exc.status_code,
        data={"reason": reason} if reason else None,
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

# 动作库媒体：/static/exercises/gifs/<id>.gif、/static/exercises/thumbs/<id>.jpg
# 目录首次启动时自建；媒体文件由 _ingest 脚本拷进来（已在 .gitignore 里排除）
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# MCP 依赖注入服务器：端点 /mcp，必须挂在所有业务路由之后，避免抢路由
if settings.MCP_ENABLED:
    mount_mcp(app)
