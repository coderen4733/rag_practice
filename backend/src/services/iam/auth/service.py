import jwt
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from src.services.iam.auth import repository as auth_repository
from src.services.iam.auth.models import RefreshToken
from src.services.iam.auth.schemas import (
    ChangePasswordReq,
    ChangePasswordRes,
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
from src.services.iam.user.models import User


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


# 비밀번호 변경(change-password) API
#  - 이 기능을 user가 아니라 auth에 만든 이유:
#    리프레시 토큰(auth 영역)을 삭제해야 하는데, user 폴더에서 auth를 import 하면
#    의존 방향 규칙(auth -> user 한 방향만 허용)을 어기게 됨
async def change_password(
    session: AsyncSession,
    dto: ChangePasswordReq,
    current_user: User,
) -> ChangePasswordRes:
    # 1. New Password Confirm Check
    if dto.new_password != dto.new_password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호가 서로 일치하지 않습니다.",
        )
    # 2. Current Password Check
    #  - 401이 아니라 400으로 응답하는 이유:
    #    401은 "로그인이 필요함(토큰 문제)"이라는 뜻이라, 프론트엔드가 401을 받으면
    #    토큰재발급이나 로그아웃 처리를 할 수 있음 => 비밀번호 오타 한 번에 로그아웃되는 문제
    #    => "요청 내용이 틀렸다"는 뜻인 400으로 응답
    if not verify_password(dto.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 일치하지 않습니다.",
        )
    # 3. Same Password Check (현재 비밀번호와 똑같은 비밀번호로는 변경 불가)
    if dto.new_password == dto.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.",
        )
    # 4. Password 변경
    # 4-1. 새 password 해시
    current_user.hashed_password = hash_password(dto.new_password)
    # 4-2. Service -> Repository (User 수정)
    await user_repository.update_user(session, current_user)
    # 5. 모든 기기에서 로그아웃 (이 사용자의 리프레시 토큰 전부 삭제)
    #  - 비밀번호를 바꾸는 이유가 "비밀번호가 유출된 것 같아서"일 수 있음
    #    => 다른 사람이 이미 로그인해 둔 기기가 있다면, 그 기기의 로그인도 끊어야 함
    #  - 지금 비밀번호를 바꾼 이 기기도 로그아웃됨 => 프론트엔드는 다시 로그인 화면으로 보내야 함
    #  - ⚠️ 이미 발급된 액세스 토큰은 만료(기본 30분)될 때까지는 계속 사용할 수 있음
    #    (액세스 토큰은 DB에 저장하지 않는 방식이라 서버가 강제로 취소할 수 없음)
    #    => 그래서 액세스 토큰의 유효기간은 짧게(30분) 두는 것이 좋음
    # 5-1. Service -> Repository (RefreshToken 전체 삭제)
    signed_out_sessions = await auth_repository.delete_refresh_tokens_by_user_id(
        session,
        current_user.id,
    )
    # 6. 저장 확정(commit)
    #  - 4번(비밀번호 변경)과 5번(토큰 삭제)을 "한 번의 commit"으로 함께 확정
    #    => 둘 중 하나라도 실패하면 둘 다 취소됨 (비밀번호만 바뀌고 토큰은 남는 상황을 막음)
    #    => repository에서 commit하지 않고 service에서 commit하는 이유가 바로 이것
    await session.commit()
    # 7. 데이터
    data = ChangePasswordRes(
        success=True,
        signed_out_sessions=signed_out_sessions,
    )
    # 8. Service -> Router
    return data
