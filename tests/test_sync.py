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


def test_push_sets_then_pull(auth_client: TestClient):
    """组数据也要能推上来：workout_sets 没有 user_id，走 session 归属"""
    me = auth_client.get("/api/users/me").json()["data"]
    session = _create_workout(auth_client, me["id"])
    set_id = str(uuid.uuid4())

    resp = auth_client.post(
        "/api/sync/push",
        json={
            "changes": {
                "workout_sets": {
                    "created": [
                        {
                            "id": set_id,
                            "session_id": session["id"],
                            "exercise_id": "bench_press",
                            "set_index": 0,
                            "weight_kg": 80,
                            "reps": 5,
                            "rpe": 8,
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

    data = auth_client.get("/api/sync/pull?last_pulled_at=0").json()
    pulled = {r["id"]: r for r in data["changes"]["workout_sets"]["created"]}
    assert set_id in pulled
    assert pulled[set_id]["exercise_id"] == "bench_press"
    assert pulled[set_id]["reps"] == 5


def test_push_set_into_others_session_is_ignored(auth_client: TestClient):
    """越权防护：不能往别人的 session 里塞组数据"""
    me = auth_client.get("/api/users/me").json()["data"]
    session = _create_workout(auth_client, me["id"])

    # 换一个用户 B 登录同一客户端
    username = f"tester_b_{uuid.uuid4().hex[:8]}"
    auth_client.post(
        "/api/auth/register",
        json={"username": username, "password": "123456", "nickname": "B"},
    )
    token_b = auth_client.post(
        "/api/auth/login",
        data={"username": username, "password": "123456"},
    ).json()["data"]["access_token"]
    auth_client.headers.update({"Authorization": f"Bearer {token_b}"})

    resp = auth_client.post(
        "/api/sync/push",
        json={
            "changes": {
                "workout_sets": {
                    "created": [
                        {
                            "id": str(uuid.uuid4()),
                            "session_id": session["id"],
                            "exercise_id": "bench_press",
                            "set_index": 0,
                            "weight_kg": 80,
                            "reps": 5,
                        }
                    ],
                    "updated": [],
                    "deleted": [],
                }
            },
            "last_pulled_at": "0",
        },
    )
    # 静默跳过（200），但 B 拉不到任何组数据
    assert resp.status_code == 200, resp.text
    data = auth_client.get("/api/sync/pull?last_pulled_at=0").json()
    assert data["changes"]["workout_sets"]["created"] == []


def test_pull_with_encoded_plus_offset(auth_client: TestClient):
    """last_pulled_at 里的 +00:00 常被解码成空格，pull 必须能容错"""
    resp = auth_client.get("/api/sync/pull?last_pulled_at=2026-09-30T10:00:00 00:00")
    assert resp.status_code == 200, resp.text
    assert "changes" in resp.json()
