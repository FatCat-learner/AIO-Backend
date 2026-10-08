from typing import Annotated

from fastapi import APIRouter, Depends

from api.v1.base import get_current_user
from models.users import User
from schemas.user import UserOut

router = APIRouter()


@router.get(
    "/me",
    response_model=UserOut,
    summary="获取当前登录用户",
)
async def read_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user
