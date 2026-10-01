from typing import Annotated  # 타입에 추가 정보를 붙일 수 있게 해주는 파이썬 표준 기능

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.response import ResponseSchema
from src.core.database import get_db_session
from src.services.iam.auth.dependencies import AdminOrManagerUser, AdminUser, CurrentUser
from src.services.iam.user import service as user_service
from src.services.iam.user.schemas import (
    UserActiveUpdateReq,
    UserCreateReq,
    UserCreateRes,
    UserReadListQuery,
    UserReadListRes,
    UserReadRes,
    UserRoleUpdateReq,
    UserUpdateRes,
)

user_router = APIRouter()


# 사용자(User) 생성(C) API - 관리자(admin) 전용
@user_router.post(
    "/",
    response_model=ResponseSchema[UserCreateRes],
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    dto: UserCreateReq,
    #  Annotated[타입, 추가정보] 방식: FastAPI 공식 문서에서 현재 권장하는 방식
    #  "session은 AsyncSession 타입이고, get_db_session으로 값을 채워줘"라는 의미
    session: Annotated[AsyncSession, Depends(get_db_session)],
    #  관리자(admin) 권한 검사
    #  액세스 토큰의 주인이 admin일 때만 이 API가 실행됨
    #  토큰이 없거나 잘못됨 => 401 / 로그인은 했지만 admin이 아님 => 403
    #  current_user에는 "지금 요청한 관리자"의 User 객체가 들어옴
    #  (지금은 사용하지 않지만, 나중에 "누가 만들었는지" 기록할 때 사용할 수 있음)
    current_user: AdminUser,
) -> dict:
    # 1. Router <- Service
    data = await user_service.create_user(
        session,
        dto,
        role=dto.role,
        is_active=True,
    )
    # 2. Router -> FrontEnd
    return {
        "message": "사용자 생성에 성공했습니다.",
        "data": data,
    }


# 사용자(User) 목록 조회(R-L) API - 관리자(admin, manager) 전용
@user_router.get(
    "/",
    response_model=ResponseSchema[UserReadListRes],
    status_code=status.HTTP_200_OK,
)
async def read_users_list(
    query: Annotated[UserReadListQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    # admin 또는 manager만 통과 (승인 대기 계정을 찾아서 승인해야 하므로 manager도 허용)
    current_user: AdminOrManagerUser,
) -> dict:
    # 1. Router <- Service
    data = await user_service.read_users_list(
        session,
        query,
    )
    # 2. Router -> FrontEnd
    return {
        "message": "사용자 목록 조회에 성공했습니다.",
        "data": data,
    }


# 내 정보 조회(R-D) API
@user_router.get(
    "/me",
    response_model=ResponseSchema[UserReadRes],
    status_code=status.HTTP_200_OK,
)
async def get_me(
    current_user: CurrentUser,
) -> dict:
    # 1. SQLAlchemy 객체 -> Pydantic Response 모델 변환
    #  - get_current_user가 이미 DB에서 User를 조회했으므로 service를 거칠 필요 없음
    data = UserReadRes.model_validate(current_user)
    # 2. Router -> FrontEnd
    return {
        "message": "내 정보 조회에 성공했습니다.",
        "data": data,
    }


# 사용자(User) 활성화(U) API - 관리자(admin, manager) 전용
@user_router.patch(
    "/{user_id}/active",
    response_model=ResponseSchema[UserUpdateRes],
    status_code=status.HTTP_200_OK,
)
async def update_user_active(
    user_id: int,
    dto: UserActiveUpdateReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    # admin 또는 manager만 통과 (토큰 없음 => 401 / 권한 부족 => 403)
    current_user: AdminOrManagerUser,
) -> dict:
    # 1. Router <- Service
    data = await user_service.update_user_active(session, user_id, dto, current_user)
    # 2. Router -> FrontEnd
    return {
        "message": "사용자 활성화 상태 변경에 성공했습니다.",
        "data": data,
    }


# 사용자(User) 권한(Role) 변경(U) API - 관리자(admin) 전용
@user_router.patch(
    "/{user_id}/role",
    response_model=ResponseSchema[UserUpdateRes],
    status_code=status.HTTP_200_OK,
)
async def update_user_role(
    user_id: int,
    dto: UserRoleUpdateReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    # admin만 통과 (토큰 없음 => 401 / 권한 부족 => 403)
    current_user: AdminUser,
) -> dict:
    # 1. Router <- Service
    data = await user_service.update_user_role(session, user_id, dto, current_user)
    # 2. Router -> FrontEnd
    return {
        "message": "사용자 권한 변경에 성공했습니다.",
        "data": data,
    }
