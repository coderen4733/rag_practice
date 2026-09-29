from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.response import ResponseSchema
from src.core.database import get_db_session
from src.services.iam.auth import service as auth_service
from src.services.iam.auth.schemas import (
    ReTokenReq,
    ReTokenRes,
    SignInReq,
    SignInRes,
    SignOutReq,
    SignOutRes,
    SignUpReq,
    SignUpRes,
)

auth_router = APIRouter()


# 계정 생성(sign-up) API
@auth_router.post(
    "/sign-up",
    response_model=ResponseSchema[SignUpRes],
    status_code=status.HTTP_201_CREATED,
)
async def sign_up(
    dto: SignUpReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    # 1. Router <- Service
    data = await auth_service.sign_up(session, dto)
    # 2. Router -> FrontEnd
    return {
        "message": "회원가입에 성공했습니다. 관리자 승인 후 로그인할 수 있습니다.",
        "data": data,
    }


# 로그인(sign-in) API
@auth_router.post(
    "/sign-in",
    response_model=ResponseSchema[SignInRes],
    status_code=status.HTTP_200_OK,
)
async def sign_in(
    dto: SignInReq,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    #  * 접속한 사용자의 IP 주소를 안전하게 꺼내도록 수정
    #  - 기존: ip_address=request.client.host
    #    => request.client는 상황에 따라(일부 테스트 도구, 프록시 환경 등) None일 수 있음
    #    => None이면 None.host 를 읽다가 AttributeError(500 에러) 발생
    #  - 변경: request.client가 있으면 host, 없으면 "unknown"을 사용
    #  - 참고: 나중에 Nginx 같은 프록시 뒤에 서버를 두면 여기에는 "프록시의 IP"가 찍힘
    #    (그때는 uvicorn 실행 옵션 --proxy-headers 등으로 실제 사용자 IP를 받도록 설정해야 함)
    ip_address = request.client.host if request.client else "unknown"
    # 1. Router <- Service
    data = await auth_service.sign_in(session, dto, ip_address=ip_address)
    # 2. Router -> FrontEnd
    return {
        "message": "로그인에 성공했습니다.",
        "data": data,
    }


# 로그아웃(sign-out) API
@auth_router.post(
    "/sign-out",
    response_model=ResponseSchema[SignOutRes],
    status_code=status.HTTP_200_OK,
)
async def sign_out(
    dto: SignOutReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    # 1. Router <- Service
    data = await auth_service.sign_out(session, dto)
    # 2. Router -> FrontEnd
    return {
        "message": "로그아웃에 성공했습니다.",
        "data": data,
    }


# 토큰재발급(re-token) API
@auth_router.post(
    "/re-token",
    response_model=ResponseSchema[ReTokenRes],
    status_code=status.HTTP_200_OK,
)
async def re_token(
    dto: ReTokenReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    # 1. Router <- Service
    data = await auth_service.re_token(session, dto)
    # 2. Router -> FrontEnd
    return {
        "message": "액세스토큰 재발급에 성공했습니다.",
        "data": data,
    }
