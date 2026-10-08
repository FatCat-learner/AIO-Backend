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
src/
├── main.py                 # FastAPI 应用入口
├── api/v1/                 # API 路由，按业务模块划分
│   ├── auth/               # 注册与登录
│   ├── health/             # 健康检查
│   ├── users/              # 用户接口
│   ├── workouts/           # 训练记录接口
│   └── sync/               # 数据同步接口
├── core/                   # 配置、数据库和安全认证
├── models/                 # SQLAlchemy 数据模型
├── schemas/                # Pydantic 请求与响应模型
├── services/               # 业务服务
├── tasks/                  # 后台任务
└── utils/                  # 通用工具

tests/                      # pytest 测试
pyproject.toml              # 项目、FastAPI、pytest 和 Ruff 配置
uv.lock                    # 锁定的依赖版本
```

FastAPI 入口在 `pyproject.toml` 中配置为 `main:app`，源码目录通过 pytest 的 `pythonpath` 配置加入导入路径。
