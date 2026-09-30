from datetime import datetime

# [수정] Literal import 추가
#  - Literal["a", "b"]: 정해진 값("a" 또는 "b")만 허용하는 타입 (정렬 기준, 정렬 방향에 사용)
from typing import Annotated, Literal

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
# 사용자 목록 조회(R-L)의 항목(items)으로도 함께 사용
class UserReadRes(BaseModel):
    # from_attributes=True:
    # SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# 사용자 목록 조회(R-L) - 요청(Query)
#  - GET /users/ 의 "쿼리 파라미터"(주소 뒤 ?a=1&b=2 부분) 형식을 한 곳에 정의
#      예) /users/?is_active=false                    => 승인 대기 계정만
#      예) /users/?sort_by=created_at&order=desc      => 최신 가입순
#      예) /users/?role=manager&email=kim&page=2      => manager 중 email에 kim 포함, 2페이지
#  - 모든 값에 기본값이 있으므로 아무것도 안 보내면 "전체 사용자, 최신 가입순, 1페이지(20명)"
#  - 필터 값이 None(기본값)이면 "그 조건으로 거르지 않음"이라는 뜻
class UserReadListQuery(BaseModel):
    # 1. 필터(Filter): 조건에 맞는 사용자만 가져오기
    is_active: bool | None = Field(
        default=None,
        description="활성화 여부로 필터 (true: 승인된 계정 / false: 승인 대기·비활성 계정)",
    )
    role: UserRole | None = Field(
        default=None,
        description="권한으로 필터 (admin / manager / user)",
    )
    email: str | None = Field(
        default=None,
        max_length=50,
        description="email 부분 검색 (대소문자 구분 없음, 예: kim => kim@a.com, Akim@b.com)",
    )
    # 2. 정렬(Sort): 어떤 순서로 가져올지
    #  - sort_by를 Literal로 제한하는 이유: 아무 컬럼 이름이나 받으면
    #    hashed_password 같은 민감한 컬럼으로 정렬해서 정보를 추측하는 공격이 가능해짐
    sort_by: Literal["created_at", "updated_at", "email", "id"] = Field(
        default="created_at",
        description="정렬 기준 (created_at: 가입일 / updated_at: 수정일 / email / id)",
    )
    order: Literal["asc", "desc"] = Field(
        default="desc",
        description="정렬 방향 (desc: 내림차순=최신순·Z→A / asc: 오름차순=오래된순·A→Z)",
    )
    # 3. 페이지네이션(Pagination): 한 번에 너무 많이 가져오지 않도록 나눠서 가져오기
    #  - 사용자가 수천 명이 되면 한 번에 전부 가져올 때 DB와 서버 모두 느려짐
    #  - ge=1: 1 이상 / le=100: 100 이하 (한 페이지 최대 100명으로 제한)
    page: int = Field(default=1, ge=1, description="페이지 번호 (1부터 시작)")
    size: int = Field(default=20, ge=1, le=100, description="한 페이지당 사용자 수 (최대 100)")


# 사용자(User) 목록 조회(R-L) - 응답(Res)
class UserReadListRes(BaseModel):
    items: list[UserReadRes]  # 현재 페이지의 사용자 목록
    total: int  # 필터 조건에 맞는 전체 사용자 수 (페이지와 상관없이)
    page: int  # 현재 페이지 번호
    size: int  # 한 페이지당 사용자 수
    total_pages: int  # 전체 페이지 수 (예: total=45, size=20 => 3페이지)


# 사용자(User) 활성화(U) - 요청(Req)
class UserActiveUpdateReq(BaseModel):
    is_active: bool = Field(
        ...,
        description="계정 활성화 여부 (true: 승인 / false: 비활성화)",
    )


# 권한(Role) 변경(U) - 요청(Req)
class UserRoleUpdateReq(BaseModel):
    role: UserRole = Field(
        ...,
        description="변경할 계정 권한 (admin / manager / user)",
    )


# 사용자(User) 수정(U) - 응답(Res)
class UserUpdateRes(BaseModel):
    # from_attributes=True:
    # SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
