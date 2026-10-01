#  * 문서(Document) API 테스트
#  - 문서 등록 -> 청크 분할 -> 임베딩 -> Qdrant 저장 전체 흐름 + 목록/상세/삭제 확인
#  - 실제 서버 대신 사용하는 것 (conftest.py의 fixture)
#    - DB      : 메모리 SQLite (db_engine, session_factory)
#    - Qdrant  : 메모리 모드 Qdrant (vector_db_client)
#    - 임베딩  : 가짜 임베딩 함수 (fake_embedding)

import pytest
from sqlalchemy import delete

from src.core import vector_db
from src.core.config import get_settings
from src.services.iam.user.enums import UserRole
from src.services.iam.user.models import User
from src.services.rag.document.chunker import split_text

settings = get_settings()


# ─────────────────────────────────────────────
# 이 파일에서 공통으로 쓰는 fixture / 도우미 함수
# ─────────────────────────────────────────────
@pytest.fixture
async def admin(make_user):
    return await make_user("admin@corp.com", role=UserRole.ADMIN)


@pytest.fixture
async def manager(make_user):
    return await make_user("manager@corp.com", role=UserRole.MANAGER)


@pytest.fixture
async def normal_user(make_user):
    return await make_user("user@corp.com", role=UserRole.USER)


#  * rag_env fixture를 conftest.py로 이동
#  - 문서 검색 테스트(test_search.py)에서도 함께 쓰기 위해 conftest.py로 옮김
#    (conftest.py의 fixture는 import 없이 모든 테스트 파일에서 사용 가능)


# 문서 업로드 API 호출 도우미
#  - files={"file": (파일이름, 파일내용(bytes), 파일종류)}: 파일 첨부(multipart) 형식으로 전송
async def upload(client, headers, filename="guide.md", content="휴가 규정입니다."):
    data = content.encode() if isinstance(content, str) else content
    return await client.post(
        "/documents/",
        files={"file": (filename, data, "text/plain")},
        headers=headers,
    )


# 테스트용 긴 문서 만들기 (청크가 여러 개로 나뉘도록)
def long_text(sentence_count=200):
    sentences = [f"{number}번 규정은 매우 중요한 내용입니다." for number in range(sentence_count)]
    return " ".join(sentences)


# ─────────────────────────────────────────────
# 1. 문서 등록 (POST /documents/) - admin, manager 전용
# ─────────────────────────────────────────────
# 등록 성공 => completed 상태 + 청크가 Qdrant에 저장되고 DB의 chunk_count와 개수가 같아야 함
async def test_upload_document_success(client, manager, auth_header, rag_env):
    text = long_text()
    expected_chunks = split_text(text, chunk_size=500, chunk_overlap=100)

    response = await upload(client, auth_header(manager), "휴가규정.md", text)

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["filename"] == "휴가규정.md"
    assert data["file_extension"] == ".md"
    assert data["status"] == "completed"
    assert data["chunk_count"] == len(expected_chunks)
    assert data["uploaded_by"] == manager.id
    assert data["error_message"] is None
    # Qdrant에 실제로 저장된 청크 개수 = DB의 chunk_count
    assert await vector_db.count_document_chunks(data["id"]) == len(expected_chunks)


# 저장된 청크의 payload(추가 정보)에 문서 id, 청크 번호, 파일명, 원문이 들어 있어야 함
#  - 청크 번호는 0부터 끝까지 빠짐없이 이어져야 함 (32개씩 나눠 저장해도)
async def test_upload_document_chunk_payload(client, admin, auth_header, rag_env, vector_db_client):
    text = long_text(sentence_count=600)  # 청크 32개 초과 => 임베딩을 여러 번 나눠서 요청
    expected_chunks = split_text(text, chunk_size=500, chunk_overlap=100)
    assert len(expected_chunks) > 32

    document_id = (await upload(client, auth_header(admin), content=text)).json()["data"]["id"]

    # scroll: 컬렉션에 저장된 포인트들을 하나씩 꺼내보는 Qdrant 기능
    points, _ = await vector_db_client.scroll(
        collection_name=settings.vector_db_collection, limit=1000, with_payload=True
    )
    payloads = sorted((point.payload for point in points), key=lambda p: p["chunk_index"])
    assert [p["chunk_index"] for p in payloads] == list(range(len(expected_chunks)))
    assert [p["text"] for p in payloads] == expected_chunks
    assert all(p["document_id"] == document_id for p in payloads)
    assert all(p["filename"] == "guide.md" for p in payloads)
    # 32개씩 나눠서 임베딩을 요청했는지 (예: 청크 40개 => 32개 + 8개 => 2번)
    assert all(len(call) <= settings.embedding_batch_size for call in rag_env.calls)
    assert len(rag_env.calls) > 1


# 권한: 토큰 없음 401 / 일반 사용자 403
async def test_upload_document_permission(client, normal_user, auth_header, rag_env):
    assert (await upload(client, headers=None)).status_code == 401
    assert (await upload(client, auth_header(normal_user))).status_code == 403


# 확장자는 대소문자 구분 없이 허용 (.MD, .TXT)
@pytest.mark.parametrize("filename", ["README.MD", "notes.txt", "메모.TXT"])
async def test_upload_document_extension_case_insensitive(
    client, admin, auth_header, rag_env, filename
):
    response = await upload(client, auth_header(admin), filename)
    assert response.status_code == 201


# 지원하지 않는 형식 => 415
@pytest.mark.parametrize("filename", ["report.pdf", "image.png", "noextension"])
async def test_upload_document_unsupported_extension(client, admin, auth_header, rag_env, filename):
    response = await upload(client, auth_header(admin), filename)
    assert response.status_code == 415


# 파일 크기 제한 초과 => 413
async def test_upload_document_too_large(client, admin, auth_header, rag_env, monkeypatch):
    # 테스트 동안만 제한을 10바이트로 줄임
    monkeypatch.setattr(settings, "document_max_file_size", 10)

    response = await upload(client, auth_header(admin), content="이 문서는 10바이트를 넘습니다.")

    assert response.status_code == 413


# 빈 파일 / 공백만 있는 파일 / 텍스트가 아닌 파일 => 400
@pytest.mark.parametrize("content", [b"", b"   \n\n  ", b"\x89PNG\x00\x00binary"])
async def test_upload_document_invalid_content(client, admin, auth_header, rag_env, content):
    response = await upload(client, auth_header(admin), "bad.txt", content)
    assert response.status_code == 400


# 한국어 Windows(CP949)로 저장된 파일도 정상적으로 읽어서 저장
async def test_upload_document_cp949(client, admin, auth_header, rag_env, vector_db_client):
    response = await upload(client, auth_header(admin), "옛날문서.txt", "연차 규정".encode("cp949"))

    assert response.status_code == 201
    points, _ = await vector_db_client.scroll(
        collection_name=settings.vector_db_collection, with_payload=True
    )
    assert points[0].payload["text"] == "연차 규정"


# 임베딩 서버 장애 => 503 + 문서는 failed 상태로 남고, 사용자에게는 내부 정보 없는 메시지만 보여줌
async def test_upload_document_embedding_failure(client, admin, auth_header, rag_env):
    rag_env.fail_after = 0  # 첫 번째 임베딩 요청부터 실패

    response = await upload(client, auth_header(admin))

    assert response.status_code == 503
    # 실패한 문서도 목록에서 확인할 수 있어야 함 (관리자가 원인을 보고 삭제 후 다시 등록)
    documents = (await client.get("/documents/", headers=auth_header(admin))).json()["data"]
    failed = documents["items"][0]
    assert failed["status"] == "failed"
    assert failed["chunk_count"] == 0
    assert failed["error_message"] == "임베딩 서버에 문제가 있어 문서를 처리하지 못했습니다."


# 중간까지 저장하다가 실패 => 이미 저장된 청크도 정리(삭제)되어야 함 (반쪽짜리 문서 방지)
async def test_upload_document_partial_failure_cleans_up(client, admin, auth_header, rag_env):
    rag_env.fail_after = 1  # 첫 번째 묶음(32개)은 저장 성공, 두 번째 묶음에서 실패

    response = await upload(client, auth_header(admin), content=long_text(sentence_count=600))

    assert response.status_code == 503
    documents = (await client.get("/documents/", headers=auth_header(admin))).json()["data"]
    document_id = documents["items"][0]["id"]
    assert await vector_db.count_document_chunks(document_id) == 0


# ─────────────────────────────────────────────
# 2. 문서 목록 / 상세 조회 - 로그인한 사용자 누구나
# ─────────────────────────────────────────────
# 일반 사용자도 목록을 볼 수 있고, 최신 등록순으로 정렬되어야 함
async def test_list_documents(client, admin, normal_user, auth_header, rag_env):
    for filename in ["a.md", "b.md", "c.md"]:
        await upload(client, auth_header(admin), filename)

    response = await client.get("/documents/", headers=auth_header(normal_user))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 3
    assert [item["filename"] for item in data["items"]] == ["c.md", "b.md", "a.md"]


# 목록 조회는 로그인이 필요함 (401)
async def test_list_documents_without_token(client, rag_env):
    assert (await client.get("/documents/")).status_code == 401


# 필터: 처리 상태 / 파일명 검색, 페이지 나누기
async def test_list_documents_filters(client, admin, auth_header, rag_env):
    headers = auth_header(admin)
    await upload(client, headers, "휴가규정.md")
    await upload(client, headers, "출장규정.md")
    rag_env.fail_after = len(rag_env.calls)  # 여기서부터 임베딩 실패
    await upload(client, headers, "휴가신청방법.txt")

    async def get_list(**params):
        response = await client.get("/documents/", params=params, headers=headers)
        return response.json()["data"]

    assert (await get_list(status="failed"))["total"] == 1
    assert (await get_list(status="completed"))["total"] == 2
    assert (await get_list(filename="휴가"))["total"] == 2
    second_page = await get_list(size=2, page=2, order="asc")
    assert second_page["total_pages"] == 2
    assert [item["filename"] for item in second_page["items"]] == ["휴가신청방법.txt"]


# 상세 조회 성공 / 없는 문서 404
async def test_read_document(client, admin, normal_user, auth_header, rag_env):
    document_id = (await upload(client, auth_header(admin))).json()["data"]["id"]

    found = await client.get(f"/documents/{document_id}", headers=auth_header(normal_user))
    missing = await client.get("/documents/99999", headers=auth_header(normal_user))

    assert found.status_code == 200
    assert found.json()["data"]["id"] == document_id
    assert missing.status_code == 404


# ─────────────────────────────────────────────
# 3. 문서 삭제 (DELETE /documents/{id}) - admin, manager 전용
# ─────────────────────────────────────────────
# 삭제 성공 => DB 정보와 Qdrant 청크가 함께 삭제되고, 다른 문서의 청크는 그대로 남아야 함
async def test_delete_document(client, admin, manager, auth_header, rag_env):
    target_id = (await upload(client, auth_header(admin), "a.md", long_text())).json()["data"]["id"]
    other_id = (await upload(client, auth_header(admin), "b.md", long_text())).json()["data"]["id"]
    other_count = await vector_db.count_document_chunks(other_id)

    response = await client.delete(f"/documents/{target_id}", headers=auth_header(manager))

    assert response.status_code == 200
    assert response.json()["data"] == {"success": True, "id": target_id}
    assert await vector_db.count_document_chunks(target_id) == 0  # 삭제한 문서의 청크
    assert await vector_db.count_document_chunks(other_id) == other_count  # 다른 문서는 그대로
    detail = await client.get(f"/documents/{target_id}", headers=auth_header(admin))
    assert detail.status_code == 404


# 권한: 일반 사용자 403 / 없는 문서 404
async def test_delete_document_permission_and_not_found(
    client, admin, normal_user, auth_header, rag_env
):
    document_id = (await upload(client, auth_header(admin))).json()["data"]["id"]

    by_user = await client.delete(f"/documents/{document_id}", headers=auth_header(normal_user))
    missing = await client.delete("/documents/99999", headers=auth_header(admin))

    assert by_user.status_code == 403
    assert missing.status_code == 404


# 업로드한 사용자가 삭제되어도 문서는 남고, uploaded_by만 비워져야 함 (ondelete="SET NULL")
async def test_document_remains_when_uploader_deleted(
    client, admin, manager, auth_header, rag_env, session_factory
):
    document_id = (await upload(client, auth_header(manager))).json()["data"]["id"]
    async with session_factory() as session:
        await session.execute(delete(User).where(User.id == manager.id))
        await session.commit()

    response = await client.get(f"/documents/{document_id}", headers=auth_header(admin))

    assert response.status_code == 200
    assert response.json()["data"]["uploaded_by"] is None
