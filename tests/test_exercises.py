"""动作库接口测试（读路径公开 + 写路径需登录）。

数据由 lifespan 里的 ensure_exercises() 从 data/exercises.seed.json 灌入，
1267 条（力量 1236 + 有氧 31），所以断言里可以写死这个总量。
"""

FIRST_ID = "0001"  # 半程仰卧起坐，default 排序（use_count 倒序 + id 正序）的第一条


def _data(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    assert body["status"] == "success"
    return body["data"]


def test_list_is_public_and_seeded(client):
    """游客（不带 token）也能读列表，且种子已灌满 1267 条。"""
    data = _data(client.get("/api/exercises"))

    assert data["total"] == 1267
    assert len(data["items"]) == 50  # 默认 limit

    first = data["items"][0]
    assert first["id"] == FIRST_ID
    assert set(first) == {
        "id",
        "zh_name",
        "en_name",
        "category",
        "body_part",
        "equipment",
        "primary_tags",
        "secondary_tags",
        "usage_tags",
        "gif",
        "thumb",
    }
    # 标签出参必须是数组（库里存的是 "abs/abs.rectus" 这种拼接串）
    assert isinstance(first["primary_tags"], list)
    assert first["primary_tags"] == ["abs", "abs.rectus"]
    # 媒体只给 URL，不打进客户端包
    assert first["gif"] == f"/static/exercises/gifs/{FIRST_ID}.gif"
    assert first["thumb"] == f"/static/exercises/thumbs/{FIRST_ID}.jpg"


def test_list_filters(client):
    """部位 / 器械 / 类别 / 关键词 / 肌群 五个筛选维度各自生效。"""
    back = _data(client.get("/api/exercises", params={"body_part": "背", "limit": 200}))
    assert back["total"] == 183
    assert {i["body_part"] for i in back["items"]} == {"背"}

    barbell = _data(
        client.get("/api/exercises", params={"equipment": "杠铃", "limit": 200})
    )
    assert barbell["total"] == 169
    assert {i["equipment"] for i in barbell["items"]} == {"杠铃"}

    cardio = _data(client.get("/api/exercises", params={"category": "有氧"}))
    assert cardio["total"] == 31
    assert {i["category"] for i in cardio["items"]} == {"有氧"}

    # 关键词同时命中中英文名
    hit = _data(client.get("/api/exercises", params={"q": "sit-up"}))
    assert hit["total"] > 0
    assert any("sit-up" in i["en_name"].lower() for i in hit["items"])

    # 肌群二级标签（back.lat）只命中背部相关动作
    lat = _data(
        client.get("/api/exercises", params={"muscle": "back.lat", "limit": 200})
    )
    assert lat["total"] > 0
    assert all(
        "back.lat" in i["primary_tags"] + i["secondary_tags"] for i in lat["items"]
    )


def test_list_pagination_and_sort(client):
    page1 = _data(client.get("/api/exercises", params={"limit": 5}))
    page2 = _data(client.get("/api/exercises", params={"limit": 5, "offset": 5}))

    assert page1["total"] == page2["total"] == 1267
    assert {i["id"] for i in page1["items"]}.isdisjoint(
        {i["id"] for i in page2["items"]}
    )

    by_name = _data(client.get("/api/exercises", params={"sort": "name", "limit": 5}))
    names = [i["zh_name"] for i in by_name["items"]]
    assert names == sorted(names)


def test_filters_group_counts(client):
    """filters 给前端左栏（部位）和顶部 chip（器械）提供分组计数。"""
    data = _data(client.get("/api/exercises/filters"))

    body_part = {row["value"]: row["count"] for row in data["body_part"]}
    assert body_part["背"] == 183
    assert body_part["有氧"] == 31
    assert sum(body_part.values()) == 1267

    equipment = {row["value"]: row["count"] for row in data["equipment"]}
    assert equipment["杠铃"] == 169

    category = {row["value"]: row["count"] for row in data["category"]}
    assert category == {"力量": 1236, "有氧": 31}


def test_detail(client):
    data = _data(client.get(f"/api/exercises/{FIRST_ID}"))

    assert data["id"] == FIRST_ID
    assert data["zh_name"] == "半程仰卧起坐"
    assert data["instructions"]
    # steps 库里存 JSON 字符串，出参必须是数组
    assert isinstance(data["steps"], list) and len(data["steps"]) >= 3
    assert data["steps"][0].startswith("平躺")
    assert "Gym visual" in data["attribution"]


def test_detail_404(client):
    resp = client.get("/api/exercises/9999")
    assert resp.status_code == 404
    assert resp.json()["status"] == "error"


def test_favorite_requires_login(client):
    assert client.post(f"/api/exercises/{FIRST_ID}/favorite").status_code == 401
    # 收藏筛选同样需要登录
    assert (
        client.get("/api/exercises", params={"favorite_user": True}).status_code == 401
    )


def test_favorite_toggle_is_idempotent(auth_client):
    first = _data(auth_client.post(f"/api/exercises/{FIRST_ID}/favorite"))
    assert first == {"exercise_id": FIRST_ID, "favorited": True}

    mine = _data(auth_client.get("/api/exercises", params={"favorite_user": True}))
    assert mine["total"] == 1
    assert mine["items"][0]["id"] == FIRST_ID

    second = _data(auth_client.post(f"/api/exercises/{FIRST_ID}/favorite"))
    assert second == {"exercise_id": FIRST_ID, "favorited": False}

    empty = _data(auth_client.get("/api/exercises", params={"favorite_user": True}))
    assert empty["total"] == 0


def test_mark_used_bumps_popularity(auth_client):
    bumped = _data(auth_client.post(f"/api/exercises/{FIRST_ID}/use"))
    assert bumped == {"id": FIRST_ID, "use_count": 1}

    top = _data(
        auth_client.get("/api/exercises", params={"sort": "popular", "limit": 1})
    )
    assert top["items"][0]["id"] == FIRST_ID
    assert top["total"] == 1267


def test_static_media_served(client):
    """动图 / 缩略图走 /static 静态目录，小程序靠 URL 加载。"""
    thumb = client.get(f"/static/exercises/thumbs/{FIRST_ID}.jpg")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    assert len(thumb.content) > 1000

    gif = client.get(f"/static/exercises/gifs/{FIRST_ID}.gif")
    assert gif.status_code == 200
    assert gif.headers["content-type"] == "image/gif"
