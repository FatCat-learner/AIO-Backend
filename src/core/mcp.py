"""随 FastAPI 一起启动的 MCP 服务器（streamable-http，端点是 /mcp）。

用途：把「调接口 + 看数据库」变成 MCP 工具，让 DSH 这类 MCP 客户端直接驱动，
省掉手工 curl / 手写测试脚本。

- 接口调用默认走进程内 ASGI 传输（httpx.ASGITransport），不用真的连 8000 端口；
- 也支持传 base_url 走真实 HTTP，用来验证网络层/鉴权头；
- 数据库工具只对 SQLite / PostgreSQL 做通用 SQL，读操作强制只读。

注意：进程内调用不会跑 lifespan，所以依赖启动时建表以外的初始化逻辑请走真实 HTTP。
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from sqlalchemy import inspect, text

from core.database import engine

INSTRUCTIONS = """\
aio-backend 调试台：查询/调用 HTTP 接口、查看和修改 SQLite/PostgreSQL 数据。
推荐顺序：list_endpoints -> describe_endpoint -> login
          -> api_request -> db_tables / db_query。
所有工具返回 JSON 字符串。写库工具必须显式 confirm=True。
"""

# mcp 2.x 里 FastMCP 已改名为 MCPServer（mcp.server.mcpserver）
mcp = MCPServer(name="aio-backend", instructions=INSTRUCTIONS)

_mount_point: Any = None


def _build_http_app() -> Any:
    """构造 streamable-http 子应用：端点 /mcp，无状态 + JSON 响应。

    无状态意味着客户端不用维护 Mcp-Session-Id，uvicorn --reload 重启后也不会掉会话。
    每次都要新建：mcp 的 StreamableHTTPSessionManager 一个实例只能 run() 一次，
    进程内第二次进 lifespan（测试里每个 TestClient 都会进一次）必须换新实例。
    """
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )


@asynccontextmanager
async def mcp_lifespan():
    """把 MCP 会话管理器的任务组挂进主应用的 lifespan。

    Starlette 的 mount 不会自动执行子应用的 lifespan，必须手动进一次；
    同时把挂载点指到这次新建的子应用上，避免重复启动同一个会话管理器。
    """
    sub_app = _build_http_app()
    if _mount_point is not None:
        _mount_point.app = sub_app
    async with sub_app.router.lifespan_context(sub_app):
        yield


def mount_mcp(app: Any) -> None:
    """挂到根路径上，实际端点是 /mcp；必须在所有业务 router 之后调用。"""
    global _mount_point
    app.mount("/", _build_http_app())
    # Starlette 的 mount() 不返回挂载点，自己从路由表里拿最后一条
    _mount_point = app.routes[-1]


# ---------------------------------------------------------------- 通用小工具


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _get_app() -> Any:
    # 延迟 import：main 在导入期就会导入本模块，提前导入会循环依赖
    from main import app

    return app


def _openapi() -> dict[str, Any]:
    """统一从 OpenAPI 取接口清单。

    新版 FastAPI 的 include_router 是惰性的（app.routes 里是 _IncludedRouter），
    直接遍历 app.routes 拿不到 APIRoute，走 openapi() 才稳。
    """
    return _get_app().openapi()


def _endpoints() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, item in _openapi().get("paths", {}).items():
        for method, operation in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            rows.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": (operation or {}).get("summary") or "",
                }
            )
    return rows


async def _login_path() -> str:
    for row in _endpoints():
        is_login_route = "login" in row["path"] and "code" not in row["path"]
        if is_login_route and row["method"] == "POST":
            return row["path"]
    return "/api/v1/auth/login"


def _safe_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:4000]


def _extract_token(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict) and data.get("access_token"):
        return str(data["access_token"])
    if body.get("access_token"):
        return str(body["access_token"])
    return None


def _client(base_url: str | None) -> httpx.AsyncClient:
    # trust_env=False：绕开本机 NO_PROXY 里的 [::1] 把 httpx 搞崩的老问题
    if base_url:
        return httpx.AsyncClient(base_url=base_url, timeout=60, trust_env=False)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_get_app()),
        base_url="http://aio-backend",
        timeout=60,
        trust_env=False,
    )


async def _fetch_token(client: httpx.AsyncClient, username: str, password: str) -> str:
    path = await _login_path()
    response = await client.post(
        path,
        data={"username": username, "password": password},
    )
    token = _extract_token(_safe_body(response))
    if not token:
        detail = f"{response.status_code} {response.text[:500]}"
        raise RuntimeError(f"登录失败（{path}）：{detail}")
    return token


# ---------------------------------------------------------------- 接口类工具


@mcp.tool()
async def list_endpoints(keyword: str = "") -> str:
    """列出所有 HTTP 接口（method + path + summary）。keyword 可选，模糊过滤。"""
    rows: list[dict[str, Any]] = []
    for item in _endpoints():
        haystack = f"{item['path']} {item['summary']}".lower()
        if keyword and keyword.lower() not in haystack:
            continue
        rows.append(item)
    return _dumps({"count": len(rows), "endpoints": rows})


@mcp.tool()
async def describe_endpoint(method: str, path: str) -> str:
    """查看某接口的入参/请求体/响应结构（取自 OpenAPI，不含真实数据）。"""
    schema = _openapi()
    item = schema.get("paths", {}).get(path)
    if item is None:
        return _dumps({"error": f"没有这个路径：{path}", "hint": "先调 list_endpoints"})
    operation = item.get(method.lower())
    if operation is None:
        return _dumps({"error": f"{path} 不支持 {method}", "methods": sorted(item)})
    return _dumps(
        {
            "summary": operation.get("summary"),
            "parameters": operation.get("parameters", []),
            "requestBody": operation.get("requestBody"),
            "responses": operation.get("responses", {}),
        }
    )


@mcp.tool()
async def login(username: str, password: str) -> str:
    """登录拿 JWT，返回 access_token；后续调用把 token 传给 api_request。"""
    async with _client(None) as client:
        path = await _login_path()
        response = await client.post(
            path,
            data={"username": username, "password": password},
        )
        body = _safe_body(response)
        return _dumps(
            {
                "status_code": response.status_code,
                "login_path": path,
                "access_token": _extract_token(body),
                "body": body,
            }
        )


@mcp.tool()
async def api_request(
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    json_body: Any = None,
    form: dict[str, Any] | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    base_url: str | None = None,
) -> str:
    """调用后端接口并返回状态码 + 响应体。

    - 默认进程内调用（ASGI），不依赖端口是否在跑；base_url 填
      http://127.0.0.1:8000 则走真实网络。
    - token 省略时，若给了 username/password 会先登录再带上 Authorization。
    - json_body 发 JSON；form 发表单（OAuth2 登录这类）。
    """
    headers: dict[str, str] = {}
    result: dict[str, Any] = {"request": f"{method.upper()} {path}"}
    async with _client(base_url) as client:
        if token is None and username and password:
            token = await _fetch_token(client, username, password)
            result["auto_login"] = True
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = await client.request(
            method.upper(),
            path,
            params=query,
            json=json_body,
            data=form,
            headers=headers,
        )
        result["status_code"] = response.status_code
        result["body"] = _safe_body(response)
    return _dumps(result)


# ---------------------------------------------------------------- 数据库工具


async def _table_names() -> list[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda c: inspect(c).get_table_names())


@mcp.tool()
async def db_tables() -> str:
    """列出数据库里所有表及其行数。"""
    rows: list[dict[str, Any]] = []
    async with engine.connect() as conn:
        for name in await _table_names():
            try:
                count = (
                    await conn.execute(text(f'SELECT COUNT(*) FROM "{name}"'))
                ).scalar()
            except Exception as exc:  # noqa: BLE001 - 单表失败不该中断整张清单
                count = f"error: {exc}"
            rows.append({"table": name, "rows": count})
    return _dumps({"count": len(rows), "tables": rows})


@mcp.tool()
async def db_columns(table: str) -> str:
    """查看某张表的字段（名称/类型/可空/默认值/主键）。"""

    def collect(conn: Any) -> list[dict[str, Any]]:
        insp = inspect(conn)
        if table not in insp.get_table_names():
            return []
        return [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column.get("nullable"),
                "default": column.get("default"),
                "primary_key": column.get("primary_key"),
            }
            for column in insp.get_columns(table)
        ]

    async with engine.connect() as conn:
        columns = await conn.run_sync(collect)
    if not columns:
        return _dumps({"error": f"没有这张表：{table}", "tables": await _table_names()})
    return _dumps({"table": table, "columns": columns})


_READ_ONLY_HEAD = re.compile(r"^\s*(select|with|explain|pragma|show)\b", re.IGNORECASE)
_WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate"
    r"|create|replace|grant|attach|vacuum)\b",
    re.IGNORECASE,
)


@mcp.tool()
async def db_query(sql: str, limit: int = 100) -> str:
    """执行只读 SQL（select/with/explain/pragma），返回前 limit 行。

    写操作请用 db_exec。
    """
    if not _READ_ONLY_HEAD.match(sql) or _WRITE_WORDS.search(sql):
        return _dumps({"error": "db_query 只允许只读语句", "sql": sql})
    async with engine.connect() as conn:
        result = await conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result.fetchmany(limit)]
        return _dumps({"rows": rows, "returned": len(rows), "limit": limit})


@mcp.tool()
async def db_exec(sql: str, confirm: bool = False) -> str:
    """执行写 SQL（insert/update/delete/DDL）。

    必须 confirm=True 才真正执行，否则只回显。
    """
    if not confirm:
        return _dumps(
            {
                "dry_run": True,
                "sql": sql,
                "hint": "确认无误后带 confirm=True 再调一次；会立即提交，无法回滚",
            }
        )
    async with engine.begin() as conn:
        result = await conn.execute(text(sql))
        return _dumps({"executed": True, "rowcount": result.rowcount, "sql": sql})
