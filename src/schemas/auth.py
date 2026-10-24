from typing import Literal

from pydantic import BaseModel

from schemas.user import UserOut

AccountType = Literal["phone", "email"]
CodeScene = Literal["register", "login", "reset"]
OAuthProvider = Literal["wechat", "qq", "douyin", "alipay", "apple", "google"]


class TokenOut(BaseModel):
    """登录成功返回：JWT + 用户信息"""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CodeSendIn(BaseModel):
    """获取验证码。开发期后端不发短信，直接把模拟码返回给前端展示。"""

    account_type: AccountType = "phone"
    account: str = ""
    scene: CodeScene = "register"


class CodeSendOut(BaseModel):
    code: str
    expires_in: int
    mock: bool = True


class CodeLoginIn(BaseModel):
    """验证码登录"""

    account_type: AccountType = "phone"
    account: str
    code: str


class ResetPasswordIn(BaseModel):
    """忘记密码：验证码校验通过后重设密码"""

    account_type: AccountType = "phone"
    account: str
    code: str
    password: str


class OAuthLoginIn(BaseModel):
    """第三方登录。开发期 code 由前端伪造，后端按 provider 建号并签发 JWT。"""

    provider: OAuthProvider
    code: str = ""
    bind_ticket: str | None = None
