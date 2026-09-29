from fastapi import HTTPException, status

#  * IntegrityError => 동시 가입 요청 시 이메일 중복 가입 방지 등
#  - DB 제약조건(unique, not null 등)을 위반했을 때 SQLAlchemy가 발생시키는 에러
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.services.iam.user import repository as user_repository
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User
from src.services.iam.user.schemas import UserCreateBase, UserCreateRes


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
