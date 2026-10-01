#  * 임베딩(Embedding) 서버 호출 담당
#  - 문장(텍스트)을 임베딩 서버에 보내서 벡터(숫자 목록)를 받아오는 기능
#    => CLAUDE.md 규칙: 임베딩을 호출하는 코드는 이 파일 한 곳에만 둠
#
# 📌 임베딩(Embedding)이란?
#  - 문장의 "의미"를 숫자 목록(벡터)으로 바꾸는 것 (bge-m3는 숫자 1024개)
#  - 의미가 비슷한 문장일수록 벡터도 비슷해짐 => Qdrant가 "비슷한 문서"를 찾을 수 있게 됨
#    예) "휴가 신청 방법" 과 "연차는 어떻게 쓰나요" => 단어는 달라도 벡터는 가까움
#
# 📌 왜 앱 안에서 계산하지 않고 별도 서버(API)에 요청하는가?
#  - 임베딩 계산은 CPU를 많이 써서, 앱 안에서 하면 그동안 다른 API(로그인 등)가 느려짐
#  - 개발(Ollama)과 납품(고객사 임베딩 서버) 모두 .env의 주소만 바꾸면 되도록 하기 위함
#  - OpenAI 호환 API 형식(POST /v1/embeddings)을 사용
#    => Ollama, TEI, vLLM 등 대부분의 임베딩 서버가 이 형식을 지원함

import httpx

from src.core.config import get_settings

# get_settings()를 호출하여 환경변수 객체 가져오기
settings = get_settings()

# 서버 전체에서 함께 쓰는 HTTP 클라이언트 (init_embedding()이 호출되기 전까지는 None)
#  - 요청마다 새로 만들지 않고 재사용해야 연결을 다시 맺는 시간이 들지 않아 빠름
_http_client: httpx.AsyncClient | None = None


# 임베딩 관련 에러 (서버 연결 실패, 응답 형식 이상, 차원 불일치 등)
class EmbeddingError(Exception):
    pass


# 임베딩 서버용 HTTP 클라이언트 생성 - src/main.py의 lifespan에서 사용
def init_embedding() -> None:
    global _http_client
    # API 키가 설정된 경우에만 인증 헤더 (Ollama처럼 키가 필요 없는 서버는 생략)
    headers = {}
    if settings.embedding_api_key:
        headers["Authorization"] = f"Bearer {settings.embedding_api_key}"
    _http_client = httpx.AsyncClient(
        # base_url: 요청 주소의 앞부분 => post("/embeddings")는 {base_url}/embeddings 로 전송됨
        base_url=settings.embedding_base_url,
        headers=headers,
        timeout=settings.embedding_timeout,  # 요청 제한 시간(초)
    )


# 서버 전체에서 함께 쓰는 HTTP 클라이언트 꺼내기
def _get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise EmbeddingError("임베딩 클라이언트가 아직 만들어지지 않았습니다.")
    return _http_client


# 여러 문장을 한 번에 벡터로 바꾸기
#  - 사용법: vectors = await embed_texts(["문장1", "문장2"])  => [[0.1, ...], [0.3, ...]]
#  - 입력 순서와 결과 순서는 항상 같음 (vectors[0]은 "문장1"의 벡터)
async def embed_texts(texts: list[str]) -> list[list[float]]:
    # 1. 보낼 문장이 없으면 서버에 요청하지 않고 빈 리스트 반환
    if not texts:
        return []
    # 2. 문장이 많으면 embedding_batch_size(기본 32개)씩 나눠서 요청
    #  - 문서 하나가 청크 수백 개로 나뉠 수 있는데, 한 번에 보내면
    #    요청이 너무 커지거나 제한 시간을 넘길 수 있기 때문
    #  - range(0, 70, 32) => 0, 32, 64 => [0:32], [32:64], [64:70] 세 묶음
    vectors = []
    batch_size = settings.embedding_batch_size
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(await _request_embeddings(batch))
    return vectors


# 문장 하나를 벡터로 바꾸기 (검색할 때 질문 문장에 사용)
async def embed_text(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]


# 임베딩 서버에 실제로 요청을 보내는 함수 (embed_texts 안에서만 사용)
async def _request_embeddings(batch: list[str]) -> list[list[float]]:
    client = _get_http_client()
    # 1. 임베딩 서버에 요청 (OpenAI 호환 형식)
    #  - 요청: {"model": "bge-m3", "input": ["문장1", "문장2"]}
    try:
        response = await client.post(
            "/embeddings",
            json={"model": settings.embedding_model, "input": batch},
        )
        # 응답 상태 코드가 4xx, 5xx(에러)이면 HTTPStatusError 발생
        response.raise_for_status()
    except httpx.HTTPStatusError as err:
        # 서버는 켜져 있지만 에러를 응답한 경우 (예: 모델 이름이 틀림 => 404)
        raise EmbeddingError(
            f"임베딩 서버가 에러를 응답했습니다. (상태 코드: {err.response.status_code})"
        ) from err
    except httpx.HTTPError as err:
        # 서버에 연결 자체가 안 되는 경우 (예: 서버가 꺼져 있음, 주소가 틀림, 시간 초과)
        raise EmbeddingError(f"임베딩 서버에 연결할 수 없습니다. ({err!r})") from err

    # 2. 응답에서 벡터 꺼내기
    #  - 응답: {"data": [{"index": 0, "embedding": [...]}, {"index": 1, "embedding": [...]}]}
    #  - index 순서대로 정렬 => 입력 문장 순서와 결과 순서를 확실히 맞춤
    try:
        items = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors = [item["embedding"] for item in items]
    except (KeyError, TypeError, ValueError) as err:
        # 응답이 OpenAI 호환 형식이 아닌 경우 (예: 주소를 /v1 없이 잘못 적음)
        raise EmbeddingError("임베딩 서버의 응답 형식이 올바르지 않습니다.") from err

    # 3. 결과 검증
    # 3-1. 보낸 문장 수와 받은 벡터 수가 같은지
    if len(vectors) != len(batch):
        raise EmbeddingError(
            f"요청한 문장 수({len(batch)})와 받은 벡터 수({len(vectors)})가 다릅니다."
        )
    # 3-2. 벡터 차원이 설정(EMBEDDING_DIM)과 같은지
    #  - 다르면 Qdrant에 저장할 수 없음 => 모델 이름이나 EMBEDDING_DIM 설정 실수를 바로 알려줌
    for vector in vectors:
        if len(vector) != settings.embedding_dim:
            raise EmbeddingError(
                f"벡터 차원({len(vector)})이 설정값 EMBEDDING_DIM({settings.embedding_dim})과 "
                "다릅니다. EMBEDDING_MODEL과 EMBEDDING_DIM 설정을 확인하세요."
            )
    return vectors


# 임베딩 서버 연결 확인용 함수 - src/main.py의 lifespan에서 사용
#  - 실제로 짧은 문장 하나를 임베딩해 봄 => 연결 + 모델 이름 + 벡터 차원을 한 번에 확인
async def check_embedding_connection() -> None:
    await embed_text("연결 확인")


# 임베딩 HTTP 클라이언트 종료 함수 - src/main.py의 lifespan에서 사용
async def close_embedding() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
