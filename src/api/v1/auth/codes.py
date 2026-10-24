"""验证码存储（开发期内存实现）

产品要求：注册 / 登录 / 重置密码的验证码先不进真实短信通道，
由后端生成模拟码返回给前端，前端用顶部弹窗展示，方便联调。
真正接短信/邮件时，把 issue_code 换成写 Redis + 调通道即可，接口形状不变。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Literal

CodeScene = Literal["register", "login", "reset"]

# (scene, account) -> (code, expire_at, attempts)
_STORE: dict[tuple[str, str], tuple[str, datetime, int]] = {}

CODE_TTL_SECONDS = 300
MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_code(scene: str, account: str) -> str:
    """生成 6 位模拟验证码并落存储，返回明文码（仅开发期这样做）。"""
    code = f"{random.randint(0, 999999):06d}"
    _STORE[(scene, account)] = (code, _now() + timedelta(seconds=CODE_TTL_SECONDS), 0)
    return code


def verify_code(scene: str, account: str, code: str) -> tuple[bool, str]:
    """校验验证码。返回 (是否通过, 失败原因)。"""
    record = _STORE.get((scene, account))
    if not record:
        return False, "验证码不存在，请先获取"

    saved, expire_at, attempts = record
    if _now() > expire_at:
        _STORE.pop((scene, account), None)
        return False, "验证码已过期，请重新获取"

    if attempts >= MAX_ATTEMPTS:
        _STORE.pop((scene, account), None)
        return False, "错误次数过多，请重新获取"

    if code != saved:
        _STORE[(scene, account)] = (saved, expire_at, attempts + 1)
        return False, "验证码不正确"

    if scene != "reset":
        # 登录 / 注册成功即失效；重置密码留到改完密码再清
        _STORE.pop((scene, account), None)
    return True, ""


def consume(scene: str, account: str) -> None:
    """一次性验证码用完后清除。"""
    _STORE.pop((scene, account), None)


def clear_all() -> None:
    """测试用：清空所有验证码。"""
    _STORE.clear()
