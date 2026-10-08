import os

# 必须在 import app 之前设置环境变量，
# 因为 core.config 在 import 时就读取 DATABASE_URL
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_aio.db"

import asyncio

import pytest
from fastapi.testclient import TestClient

from core.database import Base, engine
from main import app


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """整个测试会话开始前建表，结束后删表"""

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _drop():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(_create())
    yield
    asyncio.run(_drop())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """每个测试独立的用户名，避免冲突"""
    import uuid

    username = f"tester_{uuid.uuid4().hex[:8]}"

    client.post(
        "/api/auth/register",
        json={"username": username, "password": "123456", "nickname": "T"},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": "123456"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
