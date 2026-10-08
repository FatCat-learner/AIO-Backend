from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRegister(BaseModel):
    """注册请求体"""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    nickname: str | None = Field(default=None, max_length=50)


class UserOut(BaseModel):
    """用户响应体。绝不包含 password_hash"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    nickname: str
    created_at: datetime
