from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.services.iam.user.schemas import UserCreateBase


# 계정생성(sign-up) - 요청(Req)
class SignUpReq(UserCreateBase):
    pass


# 계정생성(sign-up) - 응답(Res)
class SignUpRes(BaseModel):
    # from_attributes=True:
    # SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


# 로그인(sign-in) - 요청(Req)
class SignInReq(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="비밀번호를 입력해 주세요.",
    )


# 로그인(sign-in) - 응답(Res)
class SignInRes(BaseModel):
    access_token: str
    refresh_token: str


# 로그아웃(sign-out) - 요청(Req)
class SignOutReq(BaseModel):
    refresh_token: str


# 로그아웃(sign-out) - 응답(Res)
class SignOutRes(BaseModel):
    success: bool = True


# 토큰재발급(re-token) - 요청(Req)
class ReTokenReq(BaseModel):
    refresh_token: str


# 토큰재발급(re-token) - 응답(Res)
class ReTokenRes(BaseModel):
    access_token: str
    token_type: str = "bearer"


# 비밀번호 변경(change-password) - 요청(Req)
class ChangePasswordReq(BaseModel):
    current_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="현재 비밀번호를 입력해 주세요.",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="새 비밀번호는 8자 이상 128자 이하여야 합니다.",
    )
    new_password_confirm: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="새 비밀번호를 재입력해 주세요.",
    )


# 비밀번호 변경(change-password) - 응답(Res)
class ChangePasswordRes(BaseModel):
    success: bool = True
    signed_out_sessions: int  # 비밀번호 변경으로 로그아웃 처리된 기기(리프레시 토큰) 수
