import jwt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    verify_password,
)
from src.services.iam.auth import repository as auth_repository
from src.services.iam.auth.models import RefreshToken
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
from src.services.iam.user import repository as user_repository
from src.services.iam.user import service as user_service
from src.services.iam.user.enums import UserRole


# 계정생성(sign-up) API
async def sign_up(
    session: AsyncSession,
    dto: SignUpReq,
) -> SignUpRes:
    # 1. Service -> User Service (계정 생성 공통 기능)
    new_user = await user_service.create_user(
        session,
        dto,
        role=UserRole.USER,
        is_active=False,
    )
    # 2. UserCreateRes -> SignUpRes 변환
    # from_attributes=True:
    # new_user(UserCreateRes)의 속성(id, email ...)을 읽어서 변환
    data = SignUpRes.model_validate(new_user, from_attributes=True)
    # 3. Service -> Router
    return data


# 로그인(sign-in) API
async def sign_in(
    session: AsyncSession,
    dto: SignInReq,
    ip_address: str,
) -> SignInRes:
    # 1. User 조회
    normalized_email = dto.email.strip().lower()
    user = await user_repository.get_user_by_email(
        session,
        normalized_email,
    )
    # 1-1. User가 없거나 비밀번호 불일치 시 => 에러(401)
    #  * User가 없을 때도 가짜 해시로 비밀번호 검증을 수행
    #  - 기존: is_password_valid = user and verify_password(...)
    #    => user가 없으면 verify_password를 건너뛰어서 응답이 훨씬 빠름
    #    => 응답 속도 차이로 "이 email이 가입되어 있는지"를 알아낼 수 있음 (타이밍 공격)
    #  - 변경: user가 없으면 DUMMY_PASSWORD_HASH(가짜 해시)로 검증 => 응답 속도를 똑같이 맞춤
    #    (가짜 해시와는 절대 일치하지 않으므로 결과는 항상 False)
    hashed_password = user.hashed_password if user else DUMMY_PASSWORD_HASH
    is_password_valid = verify_password(dto.password, hashed_password)
    if not user or not is_password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 일치하지 않습니다.",
        )
    # 1-2. 관리자 승인 여부(is_active) => False면 에러(403)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 승인 대기 중인 계정입니다.",
        )
    # 2. Token 생성
    # 2-1. AccessToken (기본값: 30분)
    access_token = create_access_token(user.id)
    # 2-2. RefreshToken (기본값: 1일)
    # 토큰과 함께 "토큰의 만료 시각"도 받아서 DB에 똑같이 저장
    refresh_token, refresh_expires_at = create_refresh_token(user.id)
    # 3. DB용 리프레시토큰 객체 생성
    refresh_token_db = RefreshToken(
        user_id=user.id,
        ip_address=ip_address,
        hashed_token=hash_token(refresh_token),
        expires_at=refresh_expires_at,
    )
    # 4. DB에 리프레시토큰 객체 저장
    # 4-1. Service -> Repository
    await auth_repository.create_refresh_token(session, refresh_token_db)
    # 4-2. 저장 확정(commit)
    await session.commit()
    # 5. 데이터
    data = SignInRes(
        access_token=access_token,
        refresh_token=refresh_token,
    )
    # 6. Service -> Router
    return data


# 로그아웃(sign-out) API
async def sign_out(
    session: AsyncSession,
    dto: SignOutReq,
) -> SignOutRes:
    # 1. RefreshToken을 DB에서 조회
    hashed_token = hash_token(dto.refresh_token)
    refresh_token_db = await auth_repository.get_refresh_token_by_hashed_token(
        session,
        hashed_token,
    )
    # 2. DB에 없는 토큰일 때 (이미 로그아웃했거나, 잘못된 토큰)
    if refresh_token_db is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 이미 만료되었거나, 토큰이 유효하지 않습니다.",
        )
    # 3. RefreshToken을 DB에서 삭제 (로그아웃 처리)
    await auth_repository.delete_refresh_token(session, refresh_token_db)
    # 4. 삭제 확정(commit)
    await session.commit()
    # 5. 데이터
    data = SignOutRes(
        success=True,
    )
    # 6. Service -> Router
    return data


# 토큰재발급(re-token) API
async def re_token(
    session: AsyncSession,
    dto: ReTokenReq,
) -> ReTokenRes:
    # 1. JWT 검증 (서명이 올바른지, 만료되지 않았는지, 리프레시 토큰이 맞는지)
    try:
        payload = decode_token(dto.refresh_token, token_type="refresh")
    except jwt.PyJWTError as err:
        # jwt.PyJWTError: PyJWT가 발생시키는 모든 토큰 검증 에러의 부모 클래스
        # (만료: ExpiredSignatureError, 위조/손상: InvalidSignatureError 등을 한 번에 처리)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 이미 만료되었거나, 토큰이 유효하지 않습니다.",
        ) from err
    # 2. DB에 저장된 토큰인지 확인
    # JWT 검증만으로는 "로그아웃한 토큰"을 걸러낼 수 없음 (서명과 만료 시각은 여전히 유효하므로)
    # 로그아웃하면 DB에서 삭제되므로, DB에 없으면 사용할 수 없는 토큰
    refresh_token_db = await auth_repository.get_refresh_token_by_hashed_token(
        session,
        hash_token(dto.refresh_token),
    )
    if refresh_token_db is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 이미 만료되었거나, 토큰이 유효하지 않습니다.",
        )
    # 3. User 확인 (토큰 발급 후에 계정이 삭제되었거나 승인이 취소되었을 수 있음)
    # payload["sub"]는 문자열이므로 int()로 숫자로 바꿔서 조회
    user = await user_repository.get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 이미 만료되었거나, 토큰이 유효하지 않습니다.",
        )
    # 4. 새 AccessToken 생성
    access_token = create_access_token(user.id)
    # 5. 데이터
    data = ReTokenRes(
        access_token=access_token,
    )
    # 6. Service -> Router
    return data
