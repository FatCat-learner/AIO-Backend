import uuid

from fastapi.testclient import TestClient


def _create_workout(client, user_id: str) -> dict:
    """辅助函数：创建一个训练记录，返回其数据"""
    session_id = str(uuid.uuid4())
    resp = client.post(
        "/api/sync/push",
        json={
            "changes": {
                "workout_sessions": {
                    "created": [
                        {
                            "id": session_id,
                            "user_id": user_id,
                            "start_time": "2026-09-30T10:00:00+00:00",
                            "total_volume": 1000,
                        }
                    ],
                    "updated": [],
                    "deleted": [],
                }
            },
            "last_pulled_at": "0",
        },
    )
    assert resp.status_code == 200, resp.text
    return {"id": session_id}


def test_push_then_pull(auth_client: TestClient):
    # 先拿到当前用户 ID
    me = auth_client.get("/api/users/me").json()["data"]

    # 推送一条记录
    created = _create_workout(auth_client, me["id"])

    # 首次拉取应包含这条记录
    resp = auth_client.get("/api/sync/pull?last_pulled_at=0")
    assert resp.status_code == 200
    data = resp.json()

    ids = [r["id"] for r in data["changes"]["workout_sessions"]["created"]]
    assert created["id"] in ids


def test_sync_validation_error_uses_standard_response(auth_client: TestClient):
    response = auth_client.post("/api/sync/push", json={})

    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "请求参数校验失败"
    assert response.json()["data"]


def test_pull_incremental(auth_client: TestClient):
    me = auth_client.get("/api/users/me").json()["data"]
    _create_workout(auth_client, me["id"])

    # 第一次拉取，拿到时间戳
    resp = auth_client.get("/api/sync/pull?last_pulled_at=0")
    ts = resp.json()["timestamp"]

    # 用这个时间戳再拉，应该没有新增
    resp = auth_client.get(f"/api/sync/pull?last_pulled_at={ts}")
    data = resp.json()
    assert data["changes"]["workout_sessions"]["created"] == []


def test_soft_delete_sync(auth_client: TestClient):
    me = auth_client.get("/api/users/me").json()["data"]
    created = _create_workout(auth_client, me["id"])

    # 通过 push 删除
    auth_client.post(
        "/api/sync/push",
        json={
            "changes": {
                "workout_sessions": {
                    "created": [],
                    "updated": [],
                    "deleted": [created["id"]],
                }
            },
            "last_pulled_at": "0",
        },
    )

    # pull 应该返回 deleted
    resp = auth_client.get("/api/sync/pull?last_pulled_at=0")
    data = resp.json()
    assert created["id"] in data["changes"]["workout_sessions"]["deleted"]
