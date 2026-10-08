from pydantic import BaseModel


class HealthOut(BaseModel):
    """健康检查响应"""

    status: str
    app: str
    version: str
