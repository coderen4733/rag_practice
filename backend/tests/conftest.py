#  * 새 파일 추가 - 모든 테스트가 함께 쓰는 "공통 준비물(fixture)" 모음
#  - 기존: 없음
#  - 변경: pytest가 테스트를 실행하기 전에 이 파일을 "자동으로" 먼저 읽음
#    => 여기에 만든 fixture는 import 없이 모든 테스트 파일에서 사용 가능
#
# 📌 fixture란?
#  - 테스트에 필요한 "준비물"을 만들어 주는 함수 (@pytest.fixture 를 붙임)
#  - 테스트 함수의 매개변수에 fixture 이름을 적으면, pytest가 자동으로 만들어서 넣어줌
#    예) async def test_xxx(client, make_user):  => client, make_user fixture가 자동으로 들어옴
#  - FastAPI의 Depends와 비슷한 개념 (필요한 것을 이름으로 요청하면 알아서 채워줌)
#  - yield가 있는 fixture: yield 앞은 "준비", yield 뒤는 "정리(뒷정리)" 코드
#
# 📌 이 테스트 환경의 핵심 원칙: 실제 DB(Supabase)에는 절대 연결하지 않음
#  - 테스트마다 "메모리 속 SQLite DB"를 새로 만들고, 테스트가 끝나면 버림
#    => 실제 데이터가 오염되지 않고, 테스트끼리 서로 영향을 주지 않으며, 빠름

import os

# 1. 테스트용 환경 변수 설정 ⚠️ 반드시 src를 import 하기 "전에" 실행되어야 함
#  - src를 import 하는 순간 config.py가 환경 변수를 읽어서 설정을 만들어버림
#  - 환경 변수는 .env 파일보다 우선순위가 높으므로, 여기서 설정한 값이 .env 값을 덮어씀
#    => .env에 무엇이 들어 있든 테스트는 항상 같은 조건에서 실행됨
#  - DB_URL: 존재하지 않는 가짜 주소 => 혹시 실수로 실제 DB 연결을 시도해도
#            Supabase가 아니라 연결 실패로 끝나므로 안전함
os.environ["DB_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["DB_ECHO"] = "false"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_SECRET"] = "test-access-token-secret-at-least-32-characters"
os.environ["REFRESH_TOKEN_SECRET"] = "test-refresh-token-secret-at-least-32-characters"
os.environ["ACCESS_TOKEN_EXPIRE"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE"] = "1"

# 2. import (환경 변수 설정 뒤에 해야 하므로 파일 중간에 위치)
#  - pyproject.toml에서 이 파일만 ruff E402(import 위치 규칙) 검사를 꺼 두었음
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime

import pytest

# httpx.AsyncClient + ASGITransport: 실제 서버를 켜지 않고 FastAPI 앱에 직접 요청을 보내는 도구
#  - 서버 시작/종료 코드(main.py의 lifespan)는 실행되지 않음
#    => lifespan의 "실제 DB 연결 체크"도 실행되지 않으므로 테스트에서 안전함
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.core.base import Base
from src.core.database import get_db_session
from src.core.security import create_access_token, hash_password
from src.main import app

# auth 모델(RefreshToken)을 import 해야 refresh_tokens 테이블이 Base.metadata에 등록됨
from src.services.iam.auth import models as auth_models  # noqa: F401
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User
from tests.constants import TEST_PASSWORD

# 테스트용 비밀번호 해시를 "한 번만" 미리 계산
#  - 비밀번호 해시(Scrypt)는 보안을 위해 일부러 느리게 만든 계산이라 한 번에 약 0.05초 걸림
#  - 사용자 30명을 만들 때마다 계산하면 테스트가 느려지므로, 미리 계산한 값을 재사용
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


# 3. 테스트용 DB 엔진 (테스트 하나마다 새로 만들고, 끝나면 버림)
@pytest.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    # 3-1. 메모리 속 SQLite DB 엔진 생성
    #  - "sqlite+aiosqlite://": 파일 없이 메모리에만 존재하는 DB (엔진을 버리면 데이터도 사라짐)
    #  - StaticPool: 연결(커넥션)을 딱 하나만 만들어서 계속 재사용
    #    => 메모리 DB는 "연결마다 서로 다른 DB"가 되므로, 하나의 연결을 공유해야 데이터가 유지됨
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)

    # 3-2. DB에 연결될 때마다 실행되는 설정
    #  - 실제 DB(Postgres)에서는 테이블이 rag_practice 스키마 안에 있음
    #    => SQLite에는 스키마가 없으므로 "rag_practice"라는 이름의 메모리 DB를 붙여서(ATTACH) 흉내냄
    #  - PRAGMA foreign_keys = ON: SQLite는 기본적으로 외래키(FK) 검사를 하지 않으므로 켜줌
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS rag_practice")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    # 3-3. 모든 테이블 생성 (users, refresh_tokens)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 3-4. 테스트에 엔진 전달 => 테스트 실행
    yield engine

    # 3-5. 뒷정리: 테스트가 끝나면 엔진 종료 (메모리 DB도 함께 사라짐)
    await engine.dispose()


# 4. 테스트용 세션 공장 (테스트용 DB 엔진에 연결된 세션을 만들어 줌)
@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


# 5. 테스트용 API 호출 도구 (client)
#  - 사용법: response = await client.post("/auth/sign-in", json={...})
@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient]:
    # 5-1. 실제 DB 세션 대신 테스트용 DB 세션을 주는 함수
    async def override_get_db_session() -> AsyncGenerator[AsyncSession]:
        async with session_factory() as session:
            yield session

    # 5-2. 의존성 바꿔치기 (dependency_overrides)
    #  - 라우터가 Depends(get_db_session)을 요청하면, 대신 override_get_db_session이 실행됨
    #    => 라우터/서비스 코드는 하나도 고치지 않고 DB만 테스트용으로 바꿀 수 있음
    app.dependency_overrides[get_db_session] = override_get_db_session

    # 5-3. 서버를 켜지 않고 앱에 직접 요청을 보내는 클라이언트 생성
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

    # 5-4. 뒷정리: 바꿔치기한 의존성을 원래대로 되돌림 (다른 테스트에 영향이 없도록)
    app.dependency_overrides.clear()


# 6. 테스트용 사용자를 DB에 바로 만들어 주는 함수 (make_user)
#  - API(회원가입 -> 관리자 승인)를 거치지 않고 원하는 상태의 사용자를 즉시 만들 수 있음
#  - 사용법: user = await make_user("a@corp.com", role=UserRole.ADMIN, is_active=True)
#  - 만든 사용자의 비밀번호는 모두 TEST_PASSWORD ("password123")
@pytest.fixture
def make_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[..., Awaitable[User]]:
    async def _make_user(
        email: str,
        *,
        role: UserRole = UserRole.USER,
        is_active: bool = True,
        created_at: datetime | None = None,
    ) -> User:
        # 가입 시각을 지정하지 않으면 "지금"으로 설정 (정렬 테스트에서는 직접 지정)
        created_at = created_at or datetime.now(UTC)
        async with session_factory() as session:
            user = User(
                email=email,
                hashed_password=TEST_PASSWORD_HASH,
                role=role,
                is_active=is_active,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(user)
            await session.commit()
            return user

    return _make_user


# 7. 특정 사용자로 로그인한 것처럼 만들어 주는 헤더 (auth_header)
#  - 로그인 API를 매번 호출하지 않고, 액세스 토큰을 바로 만들어 헤더에 넣어줌
#  - 사용법: await client.get("/users/me", headers=auth_header(user))
@pytest.fixture
def auth_header() -> Callable[[User], dict[str, str]]:
    def _auth_header(user: User) -> dict[str, str]:
        access_token = create_access_token(user.id)
        return {"Authorization": f"Bearer {access_token}"}

    return _auth_header
