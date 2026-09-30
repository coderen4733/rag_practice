import math

from fastapi import HTTPException, status

#  * IntegrityError => 동시 가입 요청 시 이메일 중복 가입 방지 등
#  - DB 제약조건(unique, not null 등)을 위반했을 때 SQLAlchemy가 발생시키는 에러
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.services.iam.user import repository as user_repository
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User
from src.services.iam.user.schemas import (
    UserActiveUpdateReq,
    UserCreateBase,
    UserCreateRes,
    UserReadListQuery,
    UserReadListRes,
    UserReadRes,
    UserRoleUpdateReq,
    UserUpdateRes,
)


# 사용자(User) 생성(C) API
#  - * (별표): 이 뒤의 매개변수는 반드시 이름을 적어서 넘겨야 함 (예: role=UserRole.USER)
#    => create_user(session, dto, UserRole.USER, False) 처럼 쓰면 에러
#    => True/False가 무슨 뜻인지 헷갈리는 실수를 막고, 기본값도 없어서 호출하는 쪽이 꼭 정하게 함
async def create_user(
    session: AsyncSession,
    dto: UserCreateBase,
    *,
    role: UserRole,
    is_active: bool,
) -> UserCreateRes:
    # 1. Password Confirm Check
    if dto.password != dto.password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="두 비밀번호가 일치하지 않습니다.",
        )

    # 2. Duplicate Check
    normalized_email = dto.email.strip().lower()  # email 공백 제거 및 소문자 통일
    existing_user = await user_repository.get_user_by_email(session, normalized_email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 존재하는 email입니다.",
        )

    # 3. Create User
    # 3-1. password 해시
    hashed_password = hash_password(dto.password)
    # 3-2. user 생성
    user = User(
        email=normalized_email,
        hashed_password=hashed_password,
        role=role,
        is_active=is_active,
    )
    #  * 사용자 생성 + commit을 try/except로 감싸서 "동시 가입" 상황 처리
    #  - 문제 상황: 같은 email로 거의 동시에 가입 요청 2개가 들어오면
    #    두 요청 모두 2번(Duplicate Check)을 통과할 수 있음 (둘 다 "아직 없음"으로 조회됨)
    #    => 늦게 저장하는 쪽은 DB의 unique 제약에 걸려 IntegrityError(409:Conlict)로 응답
    try:
        # 3-2-1. Service -> Repository
        new_user = await user_repository.create_user(session, user)
        # 3-2-S. 성공 시 commit
        await session.commit()  # 작업 확정이라는 뜻
    except IntegrityError as err:
        # 3-2-F. 실패 시 rollback
        # 실패한 트랜잭션을 취소(rollback)해야 이 세션을 다시 정상적으로 사용할 수 있음
        await session.rollback()
        # from err: 원래 에러(IntegrityError)를 함께 연결해 두어 디버깅 시 원인 추적이 가능
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 존재하는 email입니다.",
        ) from err

    # 4. Model Validate
    # SQLAlchemy 객체 -> Pydantic Response 모델 변환
    data = UserCreateRes.model_validate(new_user)

    # 5. Service -> Router
    return data


# 수정 대상 사용자 조회 + 공통 검사 함수 추가
async def _get_target_user(
    session: AsyncSession,
    user_id: int,
    current_user: User,
) -> User:
    # 1. 대상 User 조회
    target_user = await user_repository.get_user_by_id(session, user_id)
    # 1-1. 대상 User가 없을 때 => 에러(404)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="존재하지 않는 사용자입니다.",
        )
    # 1-2. 자기 자신을 변경하려고 할 때 => 에러(403)
    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="자기 자신의 계정은 변경할 수 없습니다.",
        )
    # 2. Service -> Service
    return target_user


# 사용자(User) 활성화(U) API
async def update_user_active(
    session: AsyncSession,
    user_id: int,
    dto: UserActiveUpdateReq,
    current_user: User,
) -> UserUpdateRes:
    # 1. 대상 User 조회 + 공통 검사 (존재 여부, 자기 자신 여부)
    target_user = await _get_target_user(session, user_id, current_user)
    # 2. manager 권한 제한 => 일반 사용자(user) 계정만 변경 가능
    #  - 제한이 없으면 manager가 admin 계정을 비활성화할 수 있음
    #    => "하위 권한이 상위 권한을 막는" 문제가 생기므로 admin/manager 계정은 admin만 변경 가능
    if current_user.role == UserRole.MANAGER and target_user.role != UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="매니저는 일반 사용자(user) 계정만 변경할 수 있습니다.",
        )
    # 3. is_active 변경
    #  - 비활성화(false)하면 대상 사용자는 즉시 모든 API를 사용할 수 없게 됨
    #    (get_current_user와 토큰재발급이 요청마다 DB의 is_active를 다시 확인하기 때문)
    target_user.is_active = dto.is_active
    # 4. DB 반영
    # 4-1. Service -> Repository
    updated_user = await user_repository.update_user(session, target_user)
    # 4-2. 저장 확정(commit)
    await session.commit()
    # 5. SQLAlchemy 객체 -> Pydantic Response 모델 변환
    data = UserUpdateRes.model_validate(updated_user)
    # 6. Service -> Router
    return data


# 사용자(User) 권한(Role) 변경(U) API 추가
async def update_user_role(
    session: AsyncSession,
    user_id: int,
    dto: UserRoleUpdateReq,
    current_user: User,
) -> UserUpdateRes:
    # 1. 대상 User 조회 + 공통 검사 (존재 여부, 자기 자신 여부)
    target_user = await _get_target_user(session, user_id, current_user)
    # 2. role 변경
    #  - 토큰에는 role 정보가 들어있지 않고, 요청마다 DB에서 User를 다시 조회하므로
    #    권한 변경은 대상 사용자가 다시 로그인하지 않아도 "즉시" 적용됨
    target_user.role = dto.role
    # 3. DB 반영
    # 3-1. Service -> Repository
    updated_user = await user_repository.update_user(session, target_user)
    # 3-2. 저장 확정(commit)
    await session.commit()
    # 4. SQLAlchemy 객체 -> Pydantic Response 모델 변환
    data = UserUpdateRes.model_validate(updated_user)
    # 5. Service -> Router
    return data


# 사용자(User) 목록 조회(R-L) API 추가
#  - 기존: 없음 (라우터에서 user_service.read_users_list를 호출하지만 함수가 없었음)
#  - 변경: 요청받은 필터/정렬/페이지 값으로 목록을 조회하고, 페이지 정보를 계산해서 응답
async def read_users_list(
    session: AsyncSession,
    query: UserReadListQuery,
) -> UserReadListRes:
    # 1. 페이지 번호 -> 건너뛸 개수(offset) 계산
    #  - 예) page=1, size=20 => offset=0  (1번째부터)
    #  - 예) page=3, size=20 => offset=40 (41번째부터)
    offset = (query.page - 1) * query.size
    # 2. email 검색어 정리
    #  - 가입/로그인과 똑같이 공백 제거 + 소문자로 통일
    #  - 공백만 입력한 경우("  ")는 정리하면 빈 문자열("")이 되므로 None(검색 안 함)으로 처리
    email_keyword = None
    if query.email:
        email_keyword = query.email.strip().lower() or None
    # 3. Service -> Repository
    users, total = await user_repository.get_users_list(
        session,
        is_active=query.is_active,
        role=query.role,
        email=email_keyword,
        sort_by=query.sort_by,
        order=query.order,
        offset=offset,
        limit=query.size,
    )
    # 4. 전체 페이지 수 계산
    #  - math.ceil(45 / 20) = math.ceil(2.25) = 3 페이지
    #  - 사용자가 0명이면 0 페이지
    total_pages = math.ceil(total / query.size)
    # 5. SQLAlchemy 객체 목록 -> Pydantic Response 모델 변환
    data = UserReadListRes(
        items=[UserReadRes.model_validate(user) for user in users],
        total=total,
        page=query.page,
        size=query.size,
        total_pages=total_pages,
    )
    # 6. Service -> Router
    return data
