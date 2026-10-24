def test_workout_endpoints_use_standard_response(auth_client):
    # 验证创建、列表和删除接口均将原业务结果放在统一结构的 data 字段中。
    create_response = auth_client.post("/api/workouts")

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["code"] == 200
    assert created["status"] == "success"
    assert created["data"]["id"]

    list_response = auth_client.get("/api/workouts")

    assert list_response.status_code == 200
    assert list_response.json()["data"][0]["id"] == created["data"]["id"]

    delete_response = auth_client.delete(f"/api/workouts/{created['data']['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json()["data"] == {"status": "deleted"}
