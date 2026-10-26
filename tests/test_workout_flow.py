"""训练流程（§6.11）写接口测试：加动作 → 加组 → 改组 → 完成训练。

重点覆盖三件事：
1. 容量口径：只算 done=true 的组，Σ(重量 × 次数)，finish 时落库一次
2. 两级越权：workout 不属于我、we / set 不属于这场 workout，都要 404
3. history：组行回填的「上次重量/次数」+ 个人最佳
"""

import uuid

FIRST_ID = "0001"  # 兜底动作 id（真实数据从列表接口取）


def _data(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    assert body["status"] == "success"
    return body["data"]


def _exercise_ids(client, n=2):
    items = _data(client.get("/api/exercises", params={"limit": n}))["items"]
    return [item["id"] for item in items]


def _user_headers(client, prefix="rival"):
    """再起一个独立用户，用来验证越权。"""
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/auth/register",
        json={"username": username, "password": "123456", "nickname": "R"},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": "123456"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_workout(client, headers=None):
    resp = client.post("/api/workouts", headers=headers)
    return _data(resp)["id"]


def test_full_flow_add_sets_finish_and_volume(auth_client):
    client = auth_client
    ex_id = _exercise_ids(client, 1)[0]
    wid = _create_workout(client)

    # ---- 加动作：第一次练，last 应为 null
    item = _data(
        client.post(f"/api/workouts/{wid}/exercises", json={"exercise_ids": [ex_id]})
    )["items"][0]
    assert item["exercise_id"] == ex_id
    assert item["last"] is None
    we_id = item["workout_exercise_id"]

    # ---- 逐组落库：两组做完 + 一组没做完（不计容量）
    sets = [
        {
            "workout_exercise_id": we_id,
            "weight": 60,
            "reps": 10,
            "done": True,
            "spent_sec": 45,
        },
        {
            "workout_exercise_id": we_id,
            "weight": 60,
            "reps": 10,
            "done": True,
            "spent_sec": 50,
        },
        {
            "workout_exercise_id": we_id,
            "weight": 100,
            "reps": 1,
            "done": False,
            "spent_sec": 30,
            "set_type": "warmup",
        },
    ]
    set_ids = [
        _data(client.post(f"/api/workouts/{wid}/sets", json=body))["set_id"]
        for body in sets
    ]
    assert len(set(set_ids)) == 3

    # ---- 改组：第二组加到 70×8，容量跟着变
    updated = _data(
        client.patch(f"/api/workout-sets/{set_ids[1]}", json={"weight": 70, "reps": 8})
    )
    assert updated["ok"] is True
    assert updated["set"]["weight"] == 70
    assert updated["set"]["reps"] == 8
    assert updated["set"]["done"] is True  # 改组不该把 done 冲掉

    # ---- 完成训练：600 + 560 = 1160，100×1 那组没打勾不算
    finished = _data(
        client.post(
            f"/api/workouts/{wid}/finish",
            json={"title": "胸日", "note": "状态不错", "duration_sec": 1800},
        )
    )["session"]
    assert finished["id"] == wid
    assert finished["title"] == "胸日"
    assert finished["volume"] == 1160.0
    assert finished["set_count"] == 2
    assert finished["exercise_count"] == 1
    assert finished["duration_sec"] == 1800
    assert finished["finished_at"]

    # 列表里能读到落库后的容量 / 标题 / 时长
    listed = next(row for row in _data(client.get("/api/workouts")) if row["id"] == wid)
    assert listed["total_volume"] == 1160.0
    assert listed["title"] == "胸日"
    assert listed["duration_sec"] == 1800

    # ---- history：最近一次训练 + PR（只算 done 的组）
    hist = _data(client.get(f"/api/exercises/{ex_id}/history"))
    assert hist["exercise_id"] == ex_id
    assert hist["total"] == 1
    assert hist["items"][0]["session_id"] == wid
    assert len(hist["items"][0]["sets"]) == 2  # 没打勾的组不进历史
    assert hist["last"]["weight"] == 70
    assert hist["last"]["reps"] == 8
    assert hist["pr"]["weight"] == 70
    assert hist["pr"]["reps"] == 8


def test_delete_set_and_exercise_affect_volume(auth_client):
    client = auth_client
    ex_id = _exercise_ids(client, 1)[0]
    wid = _create_workout(client)
    we_id = _data(
        client.post(f"/api/workouts/{wid}/exercises", json={"exercise_ids": [ex_id]})
    )["items"][0]["workout_exercise_id"]

    keep = _data(
        client.post(
            f"/api/workouts/{wid}/sets",
            json={"workout_exercise_id": we_id, "weight": 50, "reps": 10, "done": True},
        )
    )["set_id"]
    drop = _data(
        client.post(
            f"/api/workouts/{wid}/sets",
            json={"workout_exercise_id": we_id, "weight": 50, "reps": 10, "done": True},
        )
    )["set_id"]

    _data(client.delete(f"/api/workout-sets/{drop}"))
    # 已删的组不能再删（软删后查不到 → 404）
    assert client.delete(f"/api/workout-sets/{drop}").status_code == 404

    volume = _data(
        client.post(f"/api/workouts/{wid}/finish", json={"duration_sec": 600})
    )["session"]["volume"]
    assert volume == 500.0

    # 删动作 → 该动作下的组一起软删，容量归零
    _data(client.delete(f"/api/workouts/{wid}/exercises/{we_id}"))
    volume = _data(
        client.post(f"/api/workouts/{wid}/finish", json={"duration_sec": 600})
    )["session"]["volume"]
    assert volume == 0.0
    hist = _data(client.get(f"/api/exercises/{ex_id}/history"))
    assert hist["items"] == []

    # keep 也确实被带走了
    assert client.delete(f"/api/workout-sets/{keep}").status_code == 404


def test_add_exercises_batch_and_superset(auth_client):
    client = auth_client
    first, second = _exercise_ids(client, 2)
    wid = _create_workout(client)

    items = _data(
        client.post(
            f"/api/workouts/{wid}/exercises",
            json={"exercise_ids": [first, second], "name": "超级组 A"},
        )
    )["items"]
    assert [row["exercise_id"] for row in items] == [first, second]
    assert {row["superset_name"] for row in items} == {"超级组 A"}
    assert [row["position"] for row in items] == [0, 1]

    # 重复加同一个动作不会多出一张卡
    again = _data(
        client.post(f"/api/workouts/{wid}/exercises", json={"exercise_ids": [first]})
    )["items"]
    assert [row["workout_exercise_id"] for row in again] == [
        items[0]["workout_exercise_id"]
    ]

    # 不存在的动作 → 404，且不会写入半截
    assert (
        client.post(
            f"/api/workouts/{wid}/exercises", json={"exercise_ids": ["no-such"]}
        ).status_code
        == 404
    )

    # 改动作：备注 / 组间休息 / 顺序
    updated = _data(
        client.patch(
            f"/api/workouts/{wid}/exercises/{items[0]['workout_exercise_id']}",
            json={"note": "肩胛收紧", "rest_seconds": 90, "order": 5},
        )
    )
    assert updated["note"] == "肩胛收紧"
    assert updated["rest_seconds"] == 90
    assert updated["position"] == 5


def test_other_user_cannot_write(auth_client):
    """别人不能往我的 workout / we / set 上写（两级校验，404 不泄露存在性）。"""
    client = auth_client
    ex_id = _exercise_ids(client, 1)[0]
    wid = _create_workout(client)
    item = _data(
        client.post(f"/api/workouts/{wid}/exercises", json={"exercise_ids": [ex_id]})
    )["items"][0]
    we_id = item["workout_exercise_id"]
    set_id = _data(
        client.post(
            f"/api/workouts/{wid}/sets",
            json={"workout_exercise_id": we_id, "weight": 20, "reps": 12, "done": True},
        )
    )["set_id"]

    rival = _user_headers(client)

    # 1) 别人的 workout：加动作 / 加组 / 完成 都 404
    assert (
        client.post(
            f"/api/workouts/{wid}/exercises",
            json={"exercise_ids": [ex_id]},
            headers=rival,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/workouts/{wid}/sets",
            json={"workout_exercise_id": we_id, "weight": 1, "reps": 1},
            headers=rival,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/workouts/{wid}/finish", json={"duration_sec": 60}, headers=rival
        ).status_code
        == 404
    )

    # 2) 别人的 we：改 / 删 都 404
    assert (
        client.patch(
            f"/api/workouts/{wid}/exercises/{we_id}",
            json={"note": "hack"},
            headers=rival,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/workouts/{wid}/exercises/{we_id}", headers=rival
        ).status_code
        == 404
    )

    # 3) 别人的 set：改 / 删 都 404
    assert (
        client.patch(
            f"/api/workout-sets/{set_id}", json={"weight": 999}, headers=rival
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/workout-sets/{set_id}", headers=rival).status_code == 404
    )

    # 数据没被动过：还是 20×12 一组、没完成
    mine = next(row for row in _data(client.get("/api/workouts")) if row["id"] == wid)
    assert mine["finished_at"] is None
    assert mine["total_volume"] == 0
