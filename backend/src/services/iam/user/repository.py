from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User

#  * 정렬 기준 이름 -> 실제 DB 컬럼 연결표
#  - 요청으로 받은 정렬 기준(문자열)을 실제 컬럼으로 바꿀 때 사용
#    => 이 표에 없는 컬럼으로는 정렬할 수 없음 (schemas.py의 Literal과 이중으로 막음)
SORTABLE_COLUMNS = {
    "created_at": User.created_at,
    "updated_at": User.updated_at,
    "email": User.email,
    "id": User.id,
}


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
# 토큰재발급(re-token) 시 토큰 속 user_id로 사용자를 찾기 위해
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


# 사용자(User) 수정(U) API
#  - session.add()가 없는 이유:
#    user는 이미 get_user_by_id로 "이 세션에서 조회한 객체"라서 세션이 이미 알고 있음
#    => 속성 값만 바꾸면 세션이 변경 사항을 자동으로 기억함 (UPDATE 쿼리 대상이 됨)
async def update_user(
    session: AsyncSession,
    user: User,
) -> User:
    # 1. Repository -> DB
    # 바뀐 값을 UPDATE 쿼리로 DB에 보냄 (commit은 service에서 함)
    await session.flush()
    # 2. user 객체 갱신
    # updated_at은 onupdate=func.now() 로 "DB가" 값을 정하기 때문에,
    # flush 직후 파이썬 user 객체에는 새 값이 없음 => refresh로 DB에서 다시 읽어옴
    # (refresh 없이 user.updated_at을 읽으면 비동기 환경에서 MissingGreenlet 에러가 날 수 있음)
    await session.refresh(user)
    # 3. Repository -> Service
    return user


# 사용자(User) 목록 조회(R-L) API
#  - 필터 + 정렬 + 페이지네이션을 적용한 사용자 목록과 전체 개수를 함께 반환
#  - 반환값: (현재 페이지의 사용자 목록, 필터 조건에 맞는 전체 사용자 수)
#  - * (별표): 이 뒤의 매개변수는 반드시 이름을 적어서 넘겨야 함 (값이 많아 순서 실수를 막기 위함)
async def get_users_list(
    session: AsyncSession,
    *,
    is_active: bool | None,
    role: UserRole | None,
    email: str | None,
    sort_by: str,
    order: str,
    offset: int,
    limit: int,
) -> tuple[list[User], int]:
    # 1. 필터 조건 만들기
    #  - 값이 들어온 조건만 리스트에 추가 => 조건이 하나도 없으면 전체 사용자 조회
    conditions = []
    if is_active is not None:
        # is_active는 False도 "값이 있는 것"이므로 "is not None"으로 검사해야 함
        # (if is_active: 로 쓰면 False일 때 조건이 빠지는 버그가 생김)
        conditions.append(User.is_active == is_active)
    if role is not None:
        conditions.append(User.role == role)
    if email:
        # icontains: 대소문자 구분 없이 "포함" 검색 (SQL: email ILIKE '%kim%')
        # autoescape=True: 검색어의 %, _ 를 "특수 기호"가 아니라 "그냥 글자"로 취급
        #  => 검색어로 "%"를 보내서 모든 email이 검색되는 문제를 막음
        conditions.append(User.email.icontains(email, autoescape=True))

    # 2. Repository <- DB : 전체 개수 조회 (페이지와 상관없이 조건에 맞는 사용자 수)
    #  - where(*conditions): 리스트 안의 조건들을 모두 AND로 연결 (조건이 없으면 WHERE 없음)
    count_query = select(func.count()).select_from(User).where(*conditions)
    total = await session.scalar(count_query) or 0

    # 3. 정렬 기준 만들기
    sort_column = SORTABLE_COLUMNS[sort_by]
    if order == "desc":
        order_by = [sort_column.desc(), User.id.desc()]
    else:
        order_by = [sort_column.asc(), User.id.asc()]
    #  - User.id를 두 번째 정렬 기준으로 넣는 이유:
    #    가입 시각이 같은 사용자가 여러 명이면 DB가 매번 다른 순서로 돌려줄 수 있음
    #    => 페이지를 넘길 때 같은 사용자가 두 번 나오거나 빠지는 문제가 생김
    #    => id는 절대 겹치지 않으므로, 항상 같은 순서가 보장됨

    # 4. Repository <- DB : 현재 페이지의 사용자 목록 조회
    #  - offset: 앞에서부터 건너뛸 개수 / limit: 가져올 최대 개수
    #    예) 20명씩 3페이지 => offset=40, limit=20 => 41번째~60번째 사용자
    query = select(User).where(*conditions).order_by(*order_by).offset(offset).limit(limit)
    result = await session.execute(query)
    users = list(result.scalars().all())

    # 5. Repository -> Service
    return users, total
