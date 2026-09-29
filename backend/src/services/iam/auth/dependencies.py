# 📌 사용법 (라우터 함수의 매개변수에 추가)
#  - 로그인한 사용자면 누구나  : current_user: CurrentUser
#  - 관리자(admin)만           : current_user: AdminUser
#  - 원하는 권한 조합          : current_user: Annotated[User, Depends(require_roles(...))]
#      예) Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
#
# 📌 이 파일이 core가 아니라 auth 폴더에 있는 이유
#  - get_current_user는 User 모델과 user repository(서비스 영역)를 사용함
#  - core(서버의 기반)가 services(기능 영역)를 import 하면 의존 방향이 거꾸로 되고,
#    순환 import 에러가 생기기 쉬움 => "로그인/권한"을 담당하는 auth 폴더에 둠

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status

# HTTPBearer: 요청 헤더의 "Authorization: Bearer <토큰>" 에서 토큰 부분을 꺼내주는 도구
#  - Swagger(/docs) 화면 오른쪽 위에 🔒 Authorize 버튼이 생기고, 토큰을 붙여넣어 테스트할 수 있음
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.security import decode_token
from src.services.iam.user import repository as user_repository
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User

# auto_error=False: 토큰이 없을 때 HTTPBearer가 자동으로 에러를 내지 않고 None을 넘겨줌
#  => 에러 응답(401 + 메시지)을 아래 get_current_user에서 우리가 직접 통일된 형태로 만들기 위함
bearer_scheme = HTTPBearer(auto_error=False)

# 인증 실패 시 공통으로 사용할 에러
#  - headers의 WWW-Authenticate: "이 API는 Bearer 토큰이 필요하다"고 알려주는 HTTP 표준 헤더
#  - 실패 이유(토큰 없음/만료/위조/사용자 없음)를 자세히 알려주지 않는 이유:
#    공격자에게 "어디까지 맞았는지" 힌트를 주지 않기 위함
UNAUTHORIZED_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="로그인이 필요하거나, 토큰이 유효하지 않습니다.",
    headers={"WWW-Authenticate": "Bearer"},
)


# 로그인한 사용자 확인 (액세스 토큰 검사)
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    # 같은 요청 안에서 get_db_session을 여러 번 Depends 해도 FastAPI는 "한 번만" 실행하고
    # 같은 세션을 재사용함 => 라우터 함수가 받는 session과 이 session은 같은 객체
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    # 1. 토큰이 없을 때 (Authorization 헤더가 없거나 Bearer 형식이 아닐 때)
    if credentials is None:
        raise UNAUTHORIZED_ERROR
    # 2. 토큰 검증 (서명이 올바른지, 만료되지 않았는지, 액세스 토큰이 맞는지)
    #  - credentials.credentials: "Bearer " 뒷부분의 실제 토큰 문자열
    try:
        payload = decode_token(credentials.credentials, token_type="access")
    except jwt.PyJWTError as err:
        raise UNAUTHORIZED_ERROR from err
    # 3. User 조회 (토큰 발급 후에 계정이 삭제되었거나 승인이 취소되었을 수 있음)
    #  - payload["sub"]는 문자열이므로 int()로 숫자로 바꿔서 조회
    user = await user_repository.get_user_by_id(session, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UNAUTHORIZED_ERROR
    # 4. 검사를 통과한 User 객체를 라우터 함수에 넘겨줌
    return user


# 권한(role) 검사 의존성을 "만들어 주는" 함수
#  - require_roles(UserRole.ADMIN) 처럼 허용할 권한을 넣으면, 그 권한만 통과시키는 함수를 돌려줌
#  - *allowed_roles: 권한을 여러 개 넣을 수 있음
#    (예: require_roles(UserRole.ADMIN, UserRole.MANAGER))
def require_roles(*allowed_roles: UserRole):
    # 실제로 FastAPI가 실행하는 검사 함수
    #  - 먼저 get_current_user로 "로그인 여부"를 확인한 뒤, 이어서 "권한"을 확인함
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # 로그인은 했지만 권한이 부족한 경우 => 403(Forbidden)
        #  - 401(Unauthorized): "누구인지 모름" (로그인 필요)
        #  - 403(Forbidden)   : "누구인지는 알지만 이 기능을 쓸 권한이 없음"
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="이 기능을 사용할 권한이 없습니다.",
            )
        return current_user

    return role_checker


# 라우터에서 짧게 쓰기 위한 별명(타입 별칭)
#  - CurrentUser: 로그인한 사용자라면 누구나 통과
#  - AdminUser  : 로그인한 사용자 중 role이 admin인 경우만 통과
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
