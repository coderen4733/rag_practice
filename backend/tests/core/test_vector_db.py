# [수정] 새 파일 추가 - Vector DB(Qdrant) 연결 담당 코드(src/core/vector_db.py) 테스트
#  - 기존: 없음
#  - 변경: 컬렉션 자동 생성, 차원 확인, 클라이언트 생성 전 사용 시 에러 등을 확인
#  - 실제 Qdrant 서버 대신 conftest.py의 vector_db_client(메모리 모드)를 사용

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from src.core import vector_db
from src.core.config import get_settings

settings = get_settings()


# 서버 시작 시 컬렉션이 없으면 => 설정의 차원(1024) + 코사인 유사도로 자동 생성되어야 함
async def test_ensure_collection_creates_collection(vector_db_client):
    # vector_db_client fixture가 이미 ensure_collection()을 한 번 실행한 상태
    info = await vector_db_client.get_collection(settings.vector_db_collection)

    assert info.config.params.vectors.size == 1024
    assert info.config.params.vectors.distance == Distance.COSINE


# 서버를 여러 번 재시작해도(= ensure_collection을 여러 번 호출해도) 에러 없이 그대로 유지
async def test_ensure_collection_is_idempotent(vector_db_client):
    await vector_db.ensure_collection()
    await vector_db.ensure_collection()

    collections = (await vector_db_client.get_collections()).collections
    assert [collection.name for collection in collections] == [settings.vector_db_collection]


# 이미 있는 컬렉션의 차원이 설정과 다르면 => VectorDBError (임베딩 모델을 바꾼 상황)
async def test_ensure_collection_dimension_mismatch(monkeypatch):
    # 1. 준비: 768 차원으로 만들어진 기존 컬렉션이 있는 상황
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name=settings.vector_db_collection,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    monkeypatch.setattr(vector_db, "_client", client)

    # 2. 실행 + 3. 검증: 설정(1024)과 달라서 에러가 발생해야 함
    #  - pytest.raises(에러종류): 이 블록 안에서 해당 에러가 "발생해야" 테스트 통과
    #  - match="...": 에러 메시지에 이 글자가 포함되어 있는지도 확인
    with pytest.raises(vector_db.VectorDBError, match="EMBEDDING_DIM"):
        await vector_db.ensure_collection()
    await client.close()


# 연결 확인 함수는 정상적인 Vector DB에서 에러 없이 끝나야 함
async def test_check_vector_db_connection(vector_db_client):
    await vector_db.check_vector_db_connection()


# init_vector_db()로 클라이언트를 만들기 전에 사용하면 => VectorDBError
def test_get_client_before_init(monkeypatch):
    monkeypatch.setattr(vector_db, "_client", None)

    with pytest.raises(vector_db.VectorDBError):
        vector_db.get_vector_db_client()
