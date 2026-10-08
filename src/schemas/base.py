from pydantic import BaseModel


class PushPayload(BaseModel):
    """WatermelonDB push 请求体"""

    changes: dict
    last_pulled_at: str | None = None
