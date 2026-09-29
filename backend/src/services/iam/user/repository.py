from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.iam.user.models import User


# 사용자(User) 생성(C) API
async def create_user(
    session: AsyncSession,
    user: User,
) -> User:
    #  * add / flush / refresh 는 각각 무엇인가?
    #  - 세션(session)은 "DB에 보낼 작업을 모아두는 장바구니"라고 생각하면 쉬움
    #  - 전체 흐름: add(장바구니에 담기) -> flush(DB에 보내기) -> commit(최종 확정)

    # 1. Repository -> DB
    # 1-1. add
    session.add(user)
    #  - user 객체를 세션(장바구니)에 "담기만" 함 => 아직 DB에는 아무 쿼리도 보내지 않음
    #  - await가 없는 이유: DB와 통신하지 않는 작업이라 기다릴 필요가 없음
    # 1-2. flush
    await session.flush()
    #  - 장바구니에 담긴 작업을 실제 SQL(INSERT)로 만들어 DB에 "보냄"
    #  - 하지만 아직 commit(확정) 전이라서, 다른 사람에게는 보이지 않고 rollback(취소)도 가능
    #  - flush를 하는 이유:
    #    1) DB가 id(자동 증가 번호)를 발급해 줌 => user.id 값이 생김
    #    2) email 중복(unique 위반) 같은 에러를 이 시점에 미리 확인할 수 있음
    #  - commit은 여기서 하지 않고 Service(user/service.py)에서 함
    #    => Service가 여러 작업을 묶어서 "모두 성공 or 모두 취소"를 결정하기 위함

    # 2. user 객체 갱신
    await session.refresh(user)
    #  - DB에 저장된 최신 값을 다시 읽어와서 user 객체에 채워 넣음
    #  - 필요한 이유: server_default(DB가 채우는 기본값)로 정해진 값들은
    #    파이썬 user 객체에는 아직 들어있지 않음 (예: is_active의 false)
    #    => refresh를 해야 응답(UserCreateRes)을 만들 때 이 값들을 사용할 수 있음

    # 3. Repository -> Service
    return user


# 사용자(User) 조회(R-D) API (by email)
async def get_user_by_email(
    session: AsyncSession,
    email: str,
) -> User | None:
    # 1. Repository <- DB
    # email은 PK가 아니므로 select().where() 구문 사용 필수
    query = select(User).where(User.email == email)
    result = await session.execute(query)
    # 2. Repository -> Service
    data = result.scalar_one_or_none()  # 하나만 가져오되 없으면 None 반환
    return data


# 사용자(User) 조회(R-D) API (by id)
# 토큰재발급(re-token) 시 토큰 속 user_id로 사용자를 찾기 위해 추가
# (토큰을 발급한 뒤에 계정이 비활성화되었을 수 있으므로 매번 다시 확인해야 함)
async def get_user_by_id(
    session: AsyncSession,
    user_id: int,
) -> User | None:
    # 1. Repository <- DB
    # id는 PK이므로 session.get() 으로 간단하게 조회 가능 (없으면 None 반환)
    data = await session.get(User, user_id)
    # 2. Repository -> Service
    return data
