from typing import Annotated

from fastapi import APIRouter, Depends

from api.v1.base import get_current_user
from core.responses import success_response
from models.users import User
from schemas.base import IResponse
from schemas.user import UserOut

router = APIRouter()


@router.get(
    "/me",
    response_model=IResponse[UserOut],
    summary="获取当前登录用户",
)
async def read_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return success_response(UserOut.model_validate(current_user))
