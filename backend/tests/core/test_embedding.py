# [수정] 새 파일 추가 - 임베딩 서버 호출 코드(src/core/embedding.py) 테스트
#  - 기존: 없음
#  - 변경: 요청 형식, 나눠서 보내기(배치), 순서 보장, 각종 에러 상황을 확인
#
# 📌 실제 임베딩 서버 없이 테스트하는 방법: httpx.MockTransport
#  - HTTP 요청을 실제로 보내지 않고, 우리가 만든 "가짜 서버 함수(handler)"가 대신 응답함
#  - 가짜 서버 함수는 받은 요청을 기록해 두므로 "어떤 요청을 몇 번 보냈는지"도 확인 가능

import json

import httpx
import pytest

from src.core import embedding
from src.core.config import get_settings

settings = get_settings()


# 가짜 임베딩 서버를 만들어서 embedding 파일에 끼워 넣는 fixture
#  - 사용법: server = fake_embedding_server() / server = fake_embedding_server(dim=768)
#  - server["requests"]: 가짜 서버가 받은 요청 본문 목록 (확인용)
@pytest.fixture
def fake_embedding_server(monkeypatch):
    def _create(dim=1024, status_code=200, reverse_order=False, body=None):
        requests = []

        # 가짜 서버: 요청마다 이 함수가 실행되어 응답을 만듦
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            requests.append({"url": str(request.url), "payload": payload})
            if body is not None:  # 응답 내용을 직접 지정한 경우 (형식 오류 테스트용)
                return httpx.Response(status_code, json=body)
            # 문장마다 "몇 번째 문장인지"를 첫 번째 숫자로 넣은 가짜 벡터를 만듦
            #  => 결과 순서가 입력 순서와 같은지 확인할 수 있음
            data = [
                {"index": index, "embedding": [float(index)] + [0.0] * (dim - 1)}
                for index, _ in enumerate(payload["input"])
            ]
            if reverse_order:  # 서버가 순서를 뒤섞어서 응답하는 상황 흉내
                data.reverse()
            return httpx.Response(status_code, json={"data": data})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url=settings.embedding_base_url,
        )
        monkeypatch.setattr(embedding, "_http_client", client)
        return {"requests": requests}

    return _create


# 정상 요청 => OpenAI 호환 형식으로 {base_url}/embeddings 에 요청하고 벡터를 받아옴
async def test_embed_texts_success(fake_embedding_server):
    server = fake_embedding_server()

    vectors = await embedding.embed_texts(["문장1", "문장2"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
    request = server["requests"][0]
    assert request["url"] == "http://embedding.test/v1/embeddings"
    assert request["payload"] == {"model": "bge-m3", "input": ["문장1", "문장2"]}


# 서버가 순서를 뒤섞어 응답해도 => index 기준으로 정렬해서 입력 순서와 같아야 함
async def test_embed_texts_keeps_order(fake_embedding_server):
    fake_embedding_server(reverse_order=True)

    vectors = await embedding.embed_texts(["a", "b", "c"])

    # 가짜 벡터의 첫 번째 숫자 = 문장 번호(0, 1, 2)
    assert [vector[0] for vector in vectors] == [0.0, 1.0, 2.0]


# 문장이 많으면 => embedding_batch_size씩 나눠서 여러 번 요청해야 함
async def test_embed_texts_batches(fake_embedding_server, monkeypatch):
    server = fake_embedding_server()
    # 테스트 동안만 한 번에 2문장씩 보내도록 설정 변경
    monkeypatch.setattr(embedding.settings, "embedding_batch_size", 2)

    vectors = await embedding.embed_texts(["1", "2", "3", "4", "5"])

    assert len(vectors) == 5
    # 5문장 / 2문장씩 => 3번 요청 (2개, 2개, 1개)
    assert [len(req["payload"]["input"]) for req in server["requests"]] == [2, 2, 1]


# 보낼 문장이 없으면 => 서버에 요청하지 않고 빈 리스트
async def test_embed_texts_empty(fake_embedding_server):
    server = fake_embedding_server()

    assert await embedding.embed_texts([]) == []
    assert server["requests"] == []


# 문장 하나 임베딩 (검색 질문용)
async def test_embed_text_single(fake_embedding_server):
    fake_embedding_server()

    vector = await embedding.embed_text("휴가 신청 방법")

    assert len(vector) == 1024


# 벡터 차원이 설정(1024)과 다르면 => EmbeddingError (모델 설정 실수를 바로 알려줌)
async def test_embed_texts_dimension_mismatch(fake_embedding_server):
    fake_embedding_server(dim=768)

    with pytest.raises(embedding.EmbeddingError, match="EMBEDDING_DIM"):
        await embedding.embed_texts(["문장"])


# 서버가 에러를 응답하면 => EmbeddingError (예: 모델 이름이 틀려서 404)
async def test_embed_texts_server_error(fake_embedding_server):
    fake_embedding_server(status_code=404)

    with pytest.raises(embedding.EmbeddingError, match="404"):
        await embedding.embed_texts(["문장"])


# 응답이 OpenAI 호환 형식이 아니면 => EmbeddingError (예: 주소를 잘못 적은 경우)
async def test_embed_texts_invalid_response(fake_embedding_server):
    fake_embedding_server(body={"message": "not an embedding response"})

    with pytest.raises(embedding.EmbeddingError, match="형식"):
        await embedding.embed_texts(["문장"])


# 서버에 연결할 수 없으면 => EmbeddingError (예: 임베딩 컨테이너를 켜지 않음)
async def test_embed_texts_connection_error(monkeypatch):
    # 요청하면 무조건 "연결 실패" 에러를 내는 가짜 서버
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=settings.embedding_base_url
    )
    monkeypatch.setattr(embedding, "_http_client", client)

    with pytest.raises(embedding.EmbeddingError, match="연결할 수 없습니다"):
        await embedding.embed_texts(["문장"])


# init_embedding()으로 클라이언트를 만들기 전에 사용하면 => EmbeddingError
async def test_embed_before_init(monkeypatch):
    monkeypatch.setattr(embedding, "_http_client", None)

    with pytest.raises(embedding.EmbeddingError):
        await embedding.embed_texts(["문장"])
