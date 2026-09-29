from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.services.iam.user.enums import UserRole


# 계정 생성 요청의 공통 부모 클래스
# 공통 필드를 UserCreateBase 한 곳에 모으고, 두 스키마가 이것을 상속(물려받음)
class UserCreateBase(BaseModel):
    email: Annotated[EmailStr, Field(max_length=50)]
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="비밀번호는 8자 이상 128자 이하여야 합니다.",
    )
    password_confirm: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="비밀번호를 재입력해 주세요.",
    )


# 사용자(User) 생성(C) - 요청(Req) - 관리자 전용
class UserCreateReq(UserCreateBase):
    role: UserRole = Field(
        default=UserRole.USER,
        description="계정 권한 (admin / manager / user)",
    )


# 사용자(User) 생성(C) - 응답(Res)
class UserCreateRes(BaseModel):
    # from_attributes=True:
    # SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


# 내 정보 조회(R-D) - 응답(Res)
class UserReadRes(BaseModel):
    # from_attributes=True:
    # SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
