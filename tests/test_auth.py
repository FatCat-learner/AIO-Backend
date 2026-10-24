import uuid


def test_register_and_login(client):
    username = f"alice_{uuid.uuid4().hex[:8]}"

    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": "123456"},
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == 201
    assert resp.json()["status"] == "success"
    assert resp.json()["data"]["username"] == username

    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": "123456"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()["data"]
    assert resp.json()["message"] == "登录成功"


def test_me_requires_token(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401
    assert resp.json() == {
        "code": 401,
        "data": None,
        "message": "Not authenticated",
        "status": "error",
    }


def test_me_with_token(auth_client):
    resp = auth_client.get("/api/users/me")
    assert resp.status_code == 200
    assert resp.json()["data"]["username"].startswith("tester_")


def test_validation_error_uses_standard_response(client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "ab", "password": "short"},
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == 422
    assert resp.json()["status"] == "error"
    assert resp.json()["message"] == "请求参数校验失败"
    assert resp.json()["data"]
