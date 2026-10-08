import uuid


def test_register_and_login(client):
    username = f"alice_{uuid.uuid4().hex[:8]}"

    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": "123456"},
    )
    assert resp.status_code == 201

    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": "123456"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_me_requires_token(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_me_with_token(auth_client):
    resp = auth_client.get("/api/users/me")
    assert resp.status_code == 200
    assert resp.json()["username"].startswith("tester_")
