#  * 문서 검색(Search) API 테스트
#  - 검색 흐름(질문 임베딩 -> Qdrant 검색 -> 결과), 권한, 입력값 검사, 장애 상황 확인
#
# 📌 가짜 임베딩으로 검색을 테스트하는 원리
#  - conftest.py의 fake_embedding은 "같은 문장이면 항상 같은 벡터"를 돌려줌
#  - 그래서 등록된 청크 원문을 그대로 질문으로 넣으면, 그 청크가 유사도 1.0으로 1등이 되어야 함
#    (실제 의미 검색 품질은 scripts/evaluate_search.py로 실제 임베딩 서버를 사용해서 평가)

import pytest

from src.core import vector_db
from src.services.iam.user.enums import UserRole
from src.services.rag.document.chunker import split_text


# ─────────────────────────────────────────────
# 이 파일에서 공통으로 쓰는 fixture / 도우미 함수
# ─────────────────────────────────────────────
@pytest.fixture
async def admin(make_user):
    return await make_user("admin@corp.com", role=UserRole.ADMIN)


@pytest.fixture
async def normal_user(make_user):
    return await make_user("user@corp.com", role=UserRole.USER)


# 테스트용 문서 내용 (청크가 여러 개로 나뉘도록 길게)
def long_text(prefix, sentence_count=100):
    sentences = [
        f"{prefix} {number}번 규정은 중요한 내용입니다." for number in range(sentence_count)
    ]
    return " ".join(sentences)


# 문서 업로드 도우미 (문서 id를 돌려줌)
async def upload(client, headers, filename, text):
    response = await client.post(
        "/documents/",
        files={"file": (filename, text.encode(), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


# 검색 API 호출 도우미
async def search(client, headers, **body):
    return await client.post("/search/", json=body, headers=headers)


# ─────────────────────────────────────────────
# 1. 검색 성공
# ─────────────────────────────────────────────
# 청크 원문을 그대로 질문하면 => 그 청크가 1등, 유사도 1.0, 출처 정보가 정확해야 함
async def test_search_finds_exact_chunk(client, admin, normal_user, auth_header, rag_env):
    text = long_text("휴가")
    chunks = split_text(text, chunk_size=500, chunk_overlap=100)
    document_id = await upload(client, auth_header(admin), "휴가규정.md", text)

    # 일반 사용자도 검색 가능 (로그인만 하면 됨)
    response = await search(client, auth_header(normal_user), query=chunks[1], top_k=3)

    assert response.status_code == 200
    data = response.json()["data"]
    top = data["results"][0]
    assert top["rank"] == 1
    assert top["document_id"] == document_id
    assert top["filename"] == "휴가규정.md"
    assert top["chunk_index"] == 1
    assert top["text"] == chunks[1]
    assert top["score"] == pytest.approx(1.0)  # approx: 소수점 계산 오차를 허용하는 비교
    assert data["total"] == 3
    assert data["elapsed_ms"] >= 0


# 결과는 유사도 높은 순서로 정렬되고, 순위가 1부터 차례로 매겨져야 함
async def test_search_results_sorted(client, admin, auth_header, rag_env):
    await upload(client, auth_header(admin), "a.md", long_text("가"))

    response = await search(client, auth_header(admin), query="아무 질문", top_k=5)

    results = response.json()["data"]["results"]
    assert [result["rank"] for result in results] == [1, 2, 3, 4, 5]
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True)


# top_k를 생략하면 기본 5개
async def test_search_default_top_k(client, admin, auth_header, rag_env):
    await upload(client, auth_header(admin), "a.md", long_text("가"))

    response = await search(client, auth_header(admin), query="질문")

    data = response.json()["data"]
    assert data["top_k"] == 5
    assert len(data["results"]) == 5


# 질문 앞뒤 공백은 제거되어 검색됨
async def test_search_strips_query(client, admin, auth_header, rag_env):
    response = await search(client, auth_header(admin), query="   연차 규정   ")

    assert response.status_code == 200
    assert response.json()["data"]["query"] == "연차 규정"
    assert rag_env.calls[-1] == ["연차 규정"]  # 임베딩 서버에도 공백 제거된 질문이 전달됨


# document_ids를 지정하면 => 그 문서의 청크만 검색됨
async def test_search_filter_by_document(client, admin, auth_header, rag_env):
    headers = auth_header(admin)
    first_id = await upload(client, headers, "a.md", long_text("가"))
    second_id = await upload(client, headers, "b.md", long_text("나"))

    response = await search(client, headers, query="질문", top_k=20, document_ids=[second_id])

    results = response.json()["data"]["results"]
    assert results  # 결과가 있어야 함
    assert {result["document_id"] for result in results} == {second_id}
    assert first_id not in {result["document_id"] for result in results}


# 등록된 문서가 없으면 => 에러가 아니라 빈 결과
async def test_search_no_documents(client, admin, auth_header, rag_env):
    response = await search(client, auth_header(admin), query="질문")

    assert response.status_code == 200
    assert response.json()["data"]["results"] == []
    assert response.json()["data"]["total"] == 0


# 삭제한 문서의 청크는 검색되지 않아야 함
async def test_search_excludes_deleted_document(client, admin, auth_header, rag_env):
    headers = auth_header(admin)
    text = long_text("가")
    document_id = await upload(client, headers, "a.md", text)
    await client.delete(f"/documents/{document_id}", headers=headers)

    response = await search(client, headers, query=split_text(text, 500, 100)[0])

    assert response.json()["data"]["results"] == []


# ─────────────────────────────────────────────
# 2. 권한 / 입력값 검사
# ─────────────────────────────────────────────
# 로그인하지 않으면 401
async def test_search_without_token(client, rag_env):
    response = await client.post("/search/", json={"query": "질문"})
    assert response.status_code == 401


# 잘못된 입력값은 모두 422
@pytest.mark.parametrize(
    "body",
    [
        {},  # 질문 없음
        {"query": ""},  # 빈 질문
        {"query": "     "},  # 공백만 있는 질문 (공백 제거 후 빈 문자열)
        {"query": "가" * 501},  # 500자 초과
        {"query": "질문", "top_k": 0},  # 최소 1개
        {"query": "질문", "top_k": 21},  # 최대 20개
        {"query": "질문", "document_ids": list(range(51))},  # 문서 id 최대 50개
    ],
)
async def test_search_invalid_body(client, admin, auth_header, rag_env, body):
    response = await client.post("/search/", json=body, headers=auth_header(admin))
    assert response.status_code == 422


# ─────────────────────────────────────────────
# 3. 장애 상황
# ─────────────────────────────────────────────
# 임베딩 서버 장애 => 503 + 내부 정보 없는 메시지
async def test_search_embedding_failure(client, admin, auth_header, rag_env):
    rag_env.fail_after = 0  # 첫 번째 임베딩 요청부터 실패

    response = await search(client, auth_header(admin), query="질문")

    assert response.status_code == 503
    assert response.json()["detail"] == "임베딩 서버에 문제가 있어 검색하지 못했습니다."


# Vector DB 장애 => 503
async def test_search_vector_db_failure(client, admin, auth_header, rag_env, monkeypatch):
    # 검색 함수를 "항상 실패하는 가짜 함수"로 바꿔치기
    async def broken_search(*args, **kwargs):
        raise vector_db.VectorDBError("가짜 Vector DB 장애")

    monkeypatch.setattr(vector_db, "search_document_chunks", broken_search)

    response = await search(client, auth_header(admin), query="질문")

    assert response.status_code == 503
    assert response.json()["detail"] == "Vector DB에 문제가 있어 검색하지 못했습니다."
