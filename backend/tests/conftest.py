#  * 모든 테스트가 함께 쓰는 "공통 준비물(fixture)" 모음
#  - pytest가 테스트를 실행하기 전에 이 파일을 "자동으로" 먼저 읽음
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
#  * Vector DB / 임베딩 서버 테스트용 환경 변수
#  - VECTOR_DB_URL, EMBEDDING_BASE_URL이 필수값이 되어서 테스트용 가짜 주소를 넣음
#    => 실제 Qdrant, 임베딩 서버에는 연결하지 않음
#       (Qdrant는 아래 vector_db_client fixture의 "메모리 모드", 임베딩은 가짜 응답을 사용)
os.environ["VECTOR_DB_URL"] = "http://vector-db.test:6333"
os.environ["VECTOR_DB_API_KEY"] = ""
os.environ["VECTOR_DB_COLLECTION"] = "documents"
os.environ["EMBEDDING_BASE_URL"] = "http://embedding.test/v1"
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["EMBEDDING_MODEL"] = "bge-m3"
os.environ["EMBEDDING_DIM"] = "1024"
os.environ["EMBEDDING_BATCH_SIZE"] = "32"
# 문서 등록 설정 (.env 값과 상관없이 테스트는 항상 같은 조건으로 실행)
os.environ["DOCUMENT_MAX_FILE_SIZE"] = str(1024 * 1024)
os.environ["DOCUMENT_CHUNK_SIZE"] = "500"
os.environ["DOCUMENT_CHUNK_OVERLAP"] = "100"
# LLM / 챗봇 테스트용 환경 변수 (실제 LLM 서버에는 연결하지 않음)
os.environ["LLM_BASE_URL"] = "http://llm.test/v1"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = "test-model"
os.environ["LLM_REASONING_EFFORT"] = "none"
os.environ["LLM_EXTRA_BODY"] = "{}"
os.environ["CHAT_TOP_K"] = "5"
os.environ["CHAT_HISTORY_MESSAGES"] = "6"
os.environ["CHAT_QUERY_REWRITE"] = "true"

# 2. import (환경 변수 설정 뒤에 해야 하므로 파일 중간에 위치)
#  - pyproject.toml에서 이 파일만 ruff E402(import 위치 규칙) 검사를 꺼 두었음
import hashlib  # 가짜 임베딩 벡터를 만들 때 사용
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime

import pytest

# httpx.AsyncClient + ASGITransport: 실제 서버를 켜지 않고 FastAPI 앱에 직접 요청을 보내는 도구
#  - 서버 시작/종료 코드(main.py의 lifespan)는 실행되지 않음
#    => lifespan의 "실제 DB 연결 체크"도 실행되지 않으므로 테스트에서 안전함
from httpx import ASGITransport, AsyncClient

# Qdrant 클라이언트 import (메모리 모드 Vector DB를 만들기 위함)
from qdrant_client import AsyncQdrantClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# embedding 모듈 import (가짜 임베딩으로 바꿔치기하기 위함)
# llm 모듈 import (가짜 LLM으로 바꿔치기하기 위함)
from src.core import embedding, llm, vector_db
from src.core.base import Base
from src.core.database import get_db_session
from src.core.security import create_access_token, hash_password
from src.main import app

# auth 모델(RefreshToken)을 import 해야 refresh_tokens 테이블이 Base.metadata에 등록됨
from src.services.iam.auth import models as auth_models  # noqa: F401
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User

# 대화방/대화 메시지 모델 import
#  - conversations, chat_messages 테이블이 Base.metadata에 등록되어 테스트 DB에 만들어짐
from src.services.rag.chat import models as chat_models  # noqa: F401

# 질문 다시 쓰기 규칙 import (가짜 LLM이 "질문 다시 쓰기 요청"을 구분하기 위함)
from src.services.rag.chat.prompt import REWRITE_PROMPT

# 문서 모델 import (documents 테이블이 Base.metadata에 등록되어 테스트 DB에 만들어짐)
from src.services.rag.document import models as document_models  # noqa: F401
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


# 8. 테스트용 Vector DB (vector_db_client)
#  - 실제 Qdrant 대신 "메모리 모드" Qdrant를 만들어서 src/core/vector_db.py에 끼워 넣음
#    => get_vector_db_client()를 호출하는 모든 코드가 이 메모리 Qdrant를 사용하게 됨
#  - location=":memory:": 서버 없이 파이썬 안에서만 동작하는 Qdrant (테스트가 끝나면 사라짐)
#  - monkeypatch: pytest 기본 fixture. 변수/함수를 "테스트 동안만" 바꿔치기하고,
#    테스트가 끝나면 자동으로 원래대로 되돌려줌
#  - 사용법: async def test_xxx(vector_db_client): ...
@pytest.fixture
async def vector_db_client(monkeypatch) -> AsyncGenerator[AsyncQdrantClient]:
    client = AsyncQdrantClient(location=":memory:")
    # vector_db 파일의 _client 변수를 메모리 Qdrant로 바꿔치기
    monkeypatch.setattr(vector_db, "_client", client)
    # 실제 서버 시작 때와 똑같이 컬렉션 준비
    await vector_db.ensure_collection()
    yield client
    await client.close()


# 9. 가짜 임베딩 (fake_embedding)
#  - 실제 임베딩 서버 대신 "가짜 임베딩 함수"로 바꿔치기
#    => embedding.embed_texts()를 호출하는 모든 코드(문서 등록, 나중에 검색)가 이 가짜를 사용
#  - 가짜 벡터 규칙: 같은 문장이면 항상 같은 벡터 (문장의 SHA-256 해시값으로 숫자를 만듦)
#    => 실제 의미를 반영하지는 않지만, "저장 -> 조회" 흐름을 확인하기에는 충분함
#  - 사용법:
#      async def test_xxx(fake_embedding):
#          fake_embedding.calls            # 지금까지 임베딩 요청된 문장 묶음 목록
#          fake_embedding.fail_after = 0   # 첫 번째 요청부터 실패하게 만들기 (장애 상황 흉내)
#          fake_embedding.fail_after = 1   # 두 번째 요청부터 실패 (중간까지만 저장된 상황 흉내)
class FakeEmbedding:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []  # 요청받은 문장 묶음 기록
        self.fail_after: int | None = None  # 몇 번째 요청부터 실패할지 (None이면 실패 안 함)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # 실패 설정이 있고, 이미 그 횟수만큼 요청을 받았으면 => 임베딩 서버 장애처럼 에러 발생
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise embedding.EmbeddingError("가짜 임베딩 서버 장애")
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    # 문장 -> 1024차원 가짜 벡터 (SHA-256 해시 32바이트를 반복해서 1024개 숫자로 만듦)
    @staticmethod
    def _vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255 for i in range(1024)]


@pytest.fixture
def fake_embedding(monkeypatch) -> FakeEmbedding:
    fake = FakeEmbedding()
    # embedding 파일의 embed_texts 함수를 가짜로 바꿔치기
    #  - embed_text(문장 하나)도 내부에서 embed_texts를 호출하므로 함께 가짜가 됨
    monkeypatch.setattr(embedding, "embed_texts", fake.embed_texts)
    return fake


# 10. RAG 테스트 환경 (rag_env) - tests/rag/test_document.py에서 이동
#  - 문서 등록/검색 테스트가 함께 쓰도록 이 파일로 옮김
#  - 메모리 Qdrant(vector_db_client) + 가짜 임베딩(fake_embedding)을 한 번에 켜고,
#    가짜 임베딩 객체를 돌려줌 (fail_after 설정, calls 확인용)
#  - 사용법: async def test_xxx(client, rag_env): ...
@pytest.fixture
def rag_env(vector_db_client, fake_embedding) -> FakeEmbedding:
    return fake_embedding


# 11. 가짜 LLM (fake_llm)
#  - 실제 LLM 서버 대신 "정해진 답변"을 돌려주는 가짜 LLM으로 바꿔치기
#    => llm.chat_completion / llm.stream_chat_completion 을 호출하는 모든 코드가 이 가짜를 사용
#  - 사용법:
#      async def test_xxx(fake_llm):
#          fake_llm.answer = "연차는 3근무일 전에 신청합니다. [1]"   # 돌려줄 답변 바꾸기
#          fake_llm.calls                                             # LLM에게 보낸 메시지 기록
#          fake_llm.fail = True                                       # LLM 장애 흉내
#          fake_llm.fail_after_pieces = 2                             # 스트리밍 도중 장애 흉내
#  -  * 질문 다시 쓰기(이어서 묻는 질문) 흉내
#          fake_llm.rewritten = "신입사원의 연차는 며칠인가?"   # 다시 쓴 질문으로 돌려줄 값
#          fake_llm.rewrite_calls                               # 질문 다시 쓰기 요청 기록
#          fake_llm.rewrite_fail = True                         # 질문 다시 쓰기만 장애 흉내
#    => 질문 다시 쓰기 요청은 calls가 아니라 rewrite_calls에 따로 기록
#       (calls에는 기존처럼 "답변 요청"만 남아서 기존 테스트가 그대로 동작)
class FakeLLM:
    def __init__(self) -> None:
        self.answer = "가짜 답변입니다. [1]"
        self.calls: list[list[dict[str, str]]] = []  # 받은 메시지 목록 기록
        self.fail = False  # True면 호출하자마자 실패
        self.fail_after_pieces: int | None = None  # 스트리밍 중 몇 조각 보낸 뒤 실패할지
        # 질문 다시 쓰기 흉내용 값
        self.rewritten = "다시 쓴 질문입니다"  # 다시 쓴 질문으로 돌려줄 값
        self.rewrite_calls: list[list[dict[str, str]]] = []  # 질문 다시 쓰기 요청 기록
        self.rewrite_fail = False  # True면 질문 다시 쓰기만 실패

    async def chat_completion(self, messages: list[dict[str, str]]) -> str:
        # 질문 다시 쓰기 요청(system 메시지가 REWRITE_PROMPT)이면 다시 쓴 질문을 돌려줌
        if messages[0]["content"] == REWRITE_PROMPT:
            self.rewrite_calls.append(messages)
            if self.rewrite_fail:
                raise llm.LLMError("가짜 LLM 서버 장애 (질문 다시 쓰기)")
            return self.rewritten
        self.calls.append(messages)
        if self.fail:
            raise llm.LLMError("가짜 LLM 서버 장애")
        return self.answer

    async def stream_chat_completion(self, messages: list[dict[str, str]]):
        self.calls.append(messages)
        if self.fail:
            raise llm.LLMError("가짜 LLM 서버 장애")
        # 답변을 띄어쓰기 기준으로 나눠서 조각조각 보냄 (실제 스트리밍 흉내)
        pieces = self.answer.split(" ")
        for index, piece in enumerate(pieces):
            if self.fail_after_pieces is not None and index >= self.fail_after_pieces:
                raise llm.LLMError("가짜 LLM 서버 스트리밍 중 장애")
            # 마지막 조각이 아니면 띄어쓰기를 다시 붙여서 보냄 (합치면 원래 답변이 되도록)
            yield piece if index == len(pieces) - 1 else f"{piece} "


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm, "chat_completion", fake.chat_completion)
    monkeypatch.setattr(llm, "stream_chat_completion", fake.stream_chat_completion)
    return fake
