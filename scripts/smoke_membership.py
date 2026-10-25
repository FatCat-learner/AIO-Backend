"""P0 自检：起一次 uvicorn，登录后打会员接口，然后退出。

覆盖：套餐列表（公开）、我的会员状态、额度快照（登录态）、健康检查。
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"

proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--app-dir",
        "src",
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.STDOUT,
)


def get(path: str, token: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def post_form(path: str, data: dict) -> tuple[int, dict]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def show(tag: str, code: int, body: dict) -> None:
    print(f"{tag}: {code}")


try:
    for _ in range(40):
        try:
            urllib.request.urlopen(BASE + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.3)

    code, body = get("/api/membership/plan")
    plans = body.get("data") or []
    show("GET /plan", code, body)
    for p in plans:
        print(f"  - {p['code']}: {p['price']} 元 / {p['period']} / 权益 {len(p['limits'])} 项")

    code, body = post_form("/api/auth/login", {"username": "admin", "password": "12345"})
    token = (body.get("data") or {}).get("access_token")
    show("POST /auth/login", code, body)
    if not token:
        raise SystemExit("登录失败，后面跳过")

    code, body = get("/api/membership/me", token)
    show("GET /me", code, body)
    print("  当前套餐:", (body.get("data") or {}).get("plan_code"))

    code, body = get("/api/membership/quota", token)
    show("GET /quota", code, body)
    data = body.get("data") or {}
    print("  mode:", data.get("mode"), "| limits:", len(data.get("limits") or {}), "项")
    for it in data.get("items") or []:
        print(f"    {it['key']}: {it['used']}/{it['limit']} → {it['mode']}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
