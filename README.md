# AIO Sport Backend

基于 FastAPI、SQLAlchemy 和 uv 的 AIO Sport 后端服务。

## 环境要求

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)

## 安装依赖

```powershell
uv sync
```

`uv sync` 会根据 `pyproject.toml` 和 `uv.lock` 创建或更新项目虚拟环境。

## 配置数据库

应用通过环境变量 `DATABASE_URL` 配置数据库连接，默认配置见 `src/core/config.py`。
测试会自动使用本地 SQLite 数据库。

使用 Docker 启动 PostgreSQL、PostGIS 和 pgvector：

```powershell
docker compose build db
docker compose up -d db
```

常用 Docker 命令：

```powershell
docker compose ps                          # 查看容器状态
docker compose logs -f db                  # 查看数据库日志
docker compose exec db psql -U aio -d aio  # 进入数据库命令行
docker compose stop db                     # 停止数据库
docker compose restart db                  # 重启数据库
docker compose down                        # 停止并移除容器（保留数据卷）
docker compose down -v                     # 停止并移除容器和数据卷（会清空数据）
docker compose build --no-cache db         # 不使用缓存重新构建镜像
```

Compose 默认配置：数据库 `aio`、用户 `aio`、密码 `pass`、端口 `5432`，数据保存在 `pgdata` 数据卷中。对应连接串为 `postgresql+asyncpg://aio:pass@localhost:5432/aio`（请以 `src/core/config.py` 中实际使用的驱动为准）。

应用启动时会自动创建 PostGIS、pgvector 扩展和数据表。Compose 会基于官方 `postgis/postgis:16-3.5` 构建本地数据库镜像，并在构建过程中安装 pgvector。

向量扩展开关配置为：

```env
ENABLE_VECTOR=true
```

如果使用不包含 pgvector 的数据库镜像，请将该配置改为 `false`。真正使用向量字段时，还需要增加 `pgvector` Python 依赖和对应的 SQLAlchemy 模型字段。

例如，使用 PostgreSQL：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/aio_sport"
```

## 本地开发运行

启动开发服务器：

```powershell
uv run uvicorn main:app --reload
```

默认地址：<http://127.0.0.1:8000>

- 健康检查：<http://127.0.0.1:8000/api/health>
- Swagger 文档：<http://127.0.0.1:8000/docs>
- ReDoc 文档：<http://127.0.0.1:8000/redoc>

所有业务接口都使用 `/api` 前缀。路由按 `api/v1` 组织，但当前对外不暴露 `/v1` 前缀。

接近生产的本地启动方式：

```powershell
uv run fastapi run
```

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/auth/register` | 注册用户 |
| `POST` | `/api/auth/login` | 登录并获取 JWT |
| `GET` | `/api/users/me` | 获取当前用户，需要认证 |
| `GET` | `/api/workouts` | 获取当前用户的训练记录，需要认证 |
| `POST` | `/api/workouts` | 创建训练记录，需要认证 |
| `GET` | `/api/sync/pull` | 拉取数据同步变更 |
| `POST` | `/api/sync/push` | 推送数据同步变更 |

登录接口使用 OAuth2 表单参数：`username` 和 `password`。需要认证的请求使用 `Authorization: Bearer <token>` 请求头。

## 统一响应格式

认证、用户、训练和有氧业务接口的成功响应统一使用以下结构：

```json
{
  "code": 200,
  "data": {},
  "message": "操作成功",
  "status": "success"
}
```

`code` 是实际 HTTP 状态码，`status` 成功时为 `"success"`、失败时为 `"error"`；接口原有业务返回值放在 `data` 中。例如，登录令牌的读取路径为 `response.data.access_token`，当前用户信息的读取路径为 `response.data`。错误响应同样包含这四个字段；参数校验错误会在 `data` 中附带字段级错误详情。

健康检查和 `/api/sync/*` 成功响应保留原格式，以兼容探活工具和 WatermelonDB 同步协议。所有接口的错误响应（包括同步接口）均使用上述统一结构。

## 运行测试

```powershell
uv run pytest
```

查看详细测试输出：

```powershell
uv run pytest -v
```

## 代码检查与格式化

```powershell
uv run ruff check .
uv run ruff format --check .
```

## 项目结构

```text
.
├── src/
│   ├── main.py             # FastAPI 应用入口
│   ├── ai/                 # AI 相关功能
│   ├── api/v1/             # API 路由，按业务模块划分
│   │   ├── auth/           # 注册与登录
│   │   ├── base/           # 基础接口
│   │   ├── cardio/         # 有氧运动接口
│   │   ├── health/         # 健康检查
│   │   ├── sync/           # 数据同步接口
│   │   ├── users/          # 用户接口
│   │   └── workouts/       # 训练记录接口
│   ├── core/
│   │   ├── config.py       # 应用配置
│   │   ├── database.py     # 数据库连接与初始化
│   │   ├── mcp.py          # MCP 调试服务器（/mcp，给 DSH 用）
│   │   └── security.py     # 密码哈希与 JWT
│   ├── models/             # SQLAlchemy 模型（cardio、users、workout）
│   ├── schemas/            # Pydantic 请求与响应模型
│   ├── services/           # 业务服务（cardio_service、sync_service）
│   ├── tasks/              # 后台任务
│   └── utils/              # 通用工具
├── tests/                  # pytest 测试（auth、cardio、health、sync）
├── scripts/
│   └── dump_routes.py      # 导出路由的辅助脚本
├── docker/
│   └── postgres/
│       └── Dockerfile      # PostGIS + pgvector 数据库镜像
├── docker-compose.yml      # 本地数据库服务编排
├── pyproject.toml          # 项目、FastAPI、pytest 和 Ruff 配置
├── uv.lock                 # 锁定的依赖版本
├── aio_demo.db             # 本地 SQLite 演示数据库
├── test_aio.db             # 测试用 SQLite 数据库
├── package.json            # Node 元数据（非运行必需）
└── pnpm-lock.yaml
```

FastAPI 入口在 `pyproject.toml` 中配置为 `main:app`，源码目录通过 pytest 的 `pythonpath` 配置加入导入路径。

## MCP 调试服务器（给 DSH 用）

后端自带一个 MCP（Model Context Protocol）服务器，**跟着 `uv run uvicorn main:app` 一起启动**，
端点 `http://127.0.0.1:8000/mcp`（streamable-http，无状态，无需维护 session）。

作用：让 DSH 里的 AI 直接调接口、查数据库，不用手工 curl 或写临时脚本。

| 工具 | 作用 |
| --- | --- |
| `list_endpoints` | 列出所有接口（方法/路径/摘要），可按关键字过滤 |
| `describe_endpoint` | 看某接口的入参、请求体、响应结构（来自 OpenAPI） |
| `login` | 用账号密码登录，返回 JWT |
| `api_request` | 调接口；默认走进程内 ASGI（不用端口在跑），传 `base_url` 可走真实 HTTP；给 `username`/`password` 会自动登录带 token |
| `db_tables` | 列出所有表 + 行数 |
| `db_columns` | 看某张表的字段、类型、默认值 |
| `db_query` | 只读 SQL（select/with/explain/pragma），返回前 N 行 |
| `db_exec` | 写 SQL，必须显式 `confirm=True` 才执行 |

实现见 `src/core/mcp.py`，在 `src/main.py` 末尾挂载（`settings.MCP_ENABLED` 控制开关，
上线部署请把 `MCP_ENABLED=false` 写进 `.env`，因为它没有任何鉴权、只靠只监听 127.0.0.1 兜底）。

### 手工验证

```bash
# 0. 一条命令自检（initialize + tools/list + 三个工具各调一次）
uv run python scripts/smoke_mcp.py --port 8000

# 1. 装依赖 + 起服务（MCP 跟着一起起）
uv sync
uv run uvicorn main:app --reload

# 2. 另一个终端：列工具（initialize + tools/list）
curl -s http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

### DSH 接入

DSH 用 **stdio** 方式直接拉起 `scripts/mcp_stdio.py`（同一个工具集，复用 `src/core/mcp.py`），
进程由 DSH 自己启，不依赖 8000 端口是否已经在跑：

```yaml
- id: mcp-aio-backend
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: aio-backend
    transport: stdio
    command: 'F:\Code\AIOSport\aio-backend\.venv\Scripts\python.exe'
    args:
      - scripts/mcp_stdio.py
    cwd: 'F:\Code\AIOSport\aio-backend'
    failOnStartupError: true
```

改完**重启 DSH** 才生效（配置文件不热加载），重启后可用 `mcp__aio-backend__*` 工具。
想改回 HTTP、复用 uvicorn 里那个端点，就把 `transport: stdio` 换成
`transport: streamable-http` 加 `url: "http://127.0.0.1:8000/mcp"`；但那样必须先起后端——
客户端只在插件激活时连一次，连不上重试约 2 分钟后放弃，配 `failOnStartupError: false` 会静默失败。

