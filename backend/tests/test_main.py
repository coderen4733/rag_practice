# [수정] 새 파일 추가 - 서버 시작/종료 흐름(src/main.py의 lifespan) 테스트
#  - 기존: 없음
#  - 변경: 서버가 켜질 때 DB -> Vector DB -> 임베딩 서버 순서로 연결하고,
#          꺼질 때 모두 정리하는지 확인 (실제 서버들은 모두 가짜로 바꿔치기)
#  - 다른 테스트(client fixture)는 lifespan을 실행하지 않으므로, 여기서 따로 확인함

from unittest.mock import AsyncMock

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from src import main
from src.core import embedding, vector_db
from src.core.config import get_settings

settings = get_settings()


# 정상 임베딩 서버 흉내: 문장마다 1024차원 벡터를 응답
def ok_handler(request: httpx.Request) -> httpx.Response:
    data = [{"index": 0, "embedding": [0.1] * 1024}]
    return httpx.Response(200, json={"data": data})


# 꺼져 있는 임베딩 서버 흉내: 요청하면 연결 실패
def down_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


# 실제 서버 대신 가짜를 쓰도록 main.py의 함수들을 바꿔치기하는 도우미
#  - AsyncMock(): 호출하면 아무 일도 하지 않고 끝나는 가짜 비동기 함수 (호출 여부는 기록됨)
def patch_lifespan(monkeypatch, embedding_handler):
    # 1. DB: 연결 확인/종료를 가짜 함수로 (실제 Postgres에 연결하지 않음)
    monkeypatch.setattr(main, "check_db_connection", AsyncMock())
    monkeypatch.setattr(main, "close_db", AsyncMock())

    # 2. Vector DB: 클라이언트 생성 시 메모리 모드 Qdrant를 끼워 넣음
    def fake_init_vector_db():
        monkeypatch.setattr(vector_db, "_client", AsyncQdrantClient(location=":memory:"))

    monkeypatch.setattr(main, "init_vector_db", fake_init_vector_db)

    # 3. 임베딩: 클라이언트 생성 시 가짜 임베딩 서버를 끼워 넣음
    def fake_init_embedding():
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(embedding_handler),
            base_url=settings.embedding_base_url,
        )
        monkeypatch.setattr(embedding, "_http_client", client)

    monkeypatch.setattr(main, "init_embedding", fake_init_embedding)


# 정상 시작 => 컬렉션이 준비되고, 종료 시 클라이언트가 모두 정리되어야 함
async def test_lifespan_startup_and_shutdown(monkeypatch):
    patch_lifespan(monkeypatch, ok_handler)

    # async with lifespan(app): 서버 시작 코드 실행 -> (블록 안) -> 서버 종료 코드 실행
    async with main.lifespan(main.app):
        # 서버가 켜진 상태: 컬렉션이 자동으로 만들어져 있어야 함
        client = vector_db.get_vector_db_client()
        assert await client.collection_exists(settings.vector_db_collection)
        main.check_db_connection.assert_awaited_once()  # DB 연결 확인도 실행되었는지

    # 서버가 꺼진 상태: 클라이언트가 정리되어 있어야 함
    assert vector_db._client is None
    assert embedding._http_client is None
    main.close_db.assert_awaited_once()


# 임베딩 서버가 꺼져 있으면 => 서버 시작 자체가 실패해야 함 (Fail Fast)
async def test_lifespan_fails_when_embedding_server_down(monkeypatch):
    patch_lifespan(monkeypatch, down_handler)

    with pytest.raises(embedding.EmbeddingError):
        async with main.lifespan(main.app):
            pass  # 여기까지 오면 안 됨 (시작 단계에서 에러가 나야 함)
