from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.iam.auth.models import RefreshToken


# 리프레시 토큰(Refresh Token) 조회(R-D) by hashed_token
async def get_refresh_token_by_hashed_token(
    session: AsyncSession,
    hashed_token: str,
) -> RefreshToken | None:
    # 1. Repository <- DB
    # hashed_token은 PK이므로 session.get() 으로 간단하게 조회 가능 (없으면 None 반환)
    data = await session.get(RefreshToken, hashed_token)
    # 2. Repository -> Service
    return data


# 리프레시 토큰(Refresh Token) 목록 조회(R-L) by user_id
# scalars().all() 로 "전부" 조회해서 리스트로 반환 => 모든 기기에서 로그아웃 기능 만들 때 사용
async def get_refresh_tokens_by_user_id(
    session: AsyncSession,
    user_id: int,
) -> list[RefreshToken]:
    # 1. Repository <- DB
    query = select(RefreshToken).where(RefreshToken.user_id == user_id)
    result = await session.execute(query)
    # 2. Repository -> Service
    data = list(result.scalars().all())  # 조건에 맞는 모든 행을 리스트로 반환 (없으면 빈 리스트)
    return data


# 리프레시 토큰(Refresh Token) 생성(C)
async def create_refresh_token(
    session: AsyncSession,
    refresh_token: RefreshToken,
) -> RefreshToken:
    # 1. Repository -> DB
    session.add(refresh_token)
    await session.flush()
    # 2. refresh_token 객체 갱신
    await session.refresh(refresh_token)
    # 3. Repository -> Service
    return refresh_token


# 리프레시 토큰(Refresh Token) 삭제(D)
async def delete_refresh_token(
    session: AsyncSession,
    refresh_token: RefreshToken,
) -> bool:
    # 1. Repository -> DB
    # session.delete()에는 문자열이 아니라 "DB에서 조회한 RefreshToken 객체"를 넘겨야 함
    await session.delete(refresh_token)
    # 2. Repository -> Service
    return True


# 리프레시 토큰(Refresh Token) 전체 삭제(D) by user_id
#  - 한 사용자의 리프레시 토큰을 "한 번의 쿼리로" 모두 삭제
#    => 비밀번호 변경 시 "모든 기기에서 로그아웃" 처리에 사용
async def delete_refresh_tokens_by_user_id(
    session: AsyncSession,
    user_id: int,
) -> int:
    # 1. Repository -> DB
    # 실행되는 SQL: DELETE FROM rag_practice.refresh_tokens WHERE user_id = ?
    query = delete(RefreshToken).where(RefreshToken.user_id == user_id)
    result = await session.execute(query)
    # 2. Repository -> Service
    # rowcount: 이 쿼리로 삭제된 행(row)의 개수 (로그인되어 있던 기기 수)
    return result.rowcount
