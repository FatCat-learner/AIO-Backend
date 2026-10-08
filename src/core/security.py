from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from core.config import settings


def hash_password(password: str) -> str:
    """把明文密码哈希，存入数据库"""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文密码和数据库哈希是否匹配"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """生成 JWT，subject 一般是用户 ID"""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": subject,  # 主体：用户 ID
        "iat": now,  # 签发时间
        "exp": expire,  # 过期时间
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT。失败会抛异常，由调用方捕获"""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
