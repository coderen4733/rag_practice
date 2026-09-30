#  * Vector DB(Qdrant) 연결 담당
#  - Qdrant 클라이언트 생성 / 연결 확인 / 컬렉션 준비 / 종료를 이 파일 한 곳에서 담당
#    => CLAUDE.md 규칙: 다른 Vector DB 제품으로 바꿔야 할 때 이 파일만 수정하면 되도록 함
#
# 📌 database.py와 다르게 "서버 시작 시(lifespan)" 클라이언트를 만드는 이유
#  - Qdrant 클라이언트는 만들어지는 순간 서버에 접속해서 버전을 확인함
#  - database.py처럼 파일을 import 할 때 바로 만들면, import만 해도(예: 테스트) 서버 접속을 시도함
#  - 그래서 main.py의 lifespan에서 init_vector_db()를 호출할 때 만들고,
#    다른 코드는 get_vector_db_client()로 꺼내 씀
#
# 📌 용어
#  - 컬렉션(collection): Qdrant에서 벡터를 모아두는 곳 (DB의 "테이블" 같은 개념)
#  - 포인트(point): 컬렉션에 저장되는 데이터 1개 = 벡터 + payload(추가 정보, 예: 문서 id, 원문)

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from src.core.config import get_settings

# get_settings()를 호출하여 환경변수 객체 가져오기
settings = get_settings()

# 서버 전체에서 함께 쓰는 Qdrant 클라이언트 (init_vector_db()가 호출되기 전까지는 None)
#  - 앞에 _(언더바): "이 파일 안에서만 직접 다루는 변수"라는 파이썬의 관례
#    => 다른 파일에서는 get_vector_db_client()로 꺼내 써야 함
_client: AsyncQdrantClient | None = None


# Vector DB 관련 에러 (설정이 잘못되었을 때 원인을 알기 쉽게 하기 위한 전용 에러)
class VectorDBError(Exception):
    pass


# Qdrant 클라이언트 생성 - src/main.py의 lifespan에서 사용
def init_vector_db() -> None:
    # global: 함수 안에서 파일 맨 위의 _client 변수 "자체"를 바꾸겠다는 뜻
    #  (global 없이 _client = ... 라고 쓰면 함수 안에서만 쓰는 새 변수가 만들어짐)
    global _client
    _client = AsyncQdrantClient(
        url=settings.vector_db_url,  # Qdrant 접속 주소
        api_key=settings.vector_db_api_key,  # API 키 (없으면 None)
        timeout=settings.vector_db_timeout,  # 요청 제한 시간(초)
    )


# 서버 전체에서 함께 쓰는 Qdrant 클라이언트 꺼내기
#  - 앞으로 문서 저장/검색 코드에서 이 함수로 클라이언트를 가져와서 사용
def get_vector_db_client() -> AsyncQdrantClient:
    if _client is None:
        # init_vector_db()를 호출하지 않고 사용하려는 경우 (코드 순서 실수)
        raise VectorDBError("Vector DB 클라이언트가 아직 만들어지지 않았습니다.")
    return _client


# Vector DB 연결 확인용 함수 - src/main.py의 lifespan에서 사용
async def check_vector_db_connection() -> None:
    client = get_vector_db_client()
    # 컬렉션 목록 조회가 성공하면 "연결 + 인증(API 키)"이 정상이라는 뜻
    await client.get_collections()


# 문서 벡터를 저장할 컬렉션 준비 - src/main.py의 lifespan에서 사용
#  - 컬렉션이 없으면: 설정(EMBEDDING_DIM)의 차원으로 새로 만듦
#  - 컬렉션이 있으면: 벡터 차원이 설정과 같은지 확인 (다르면 에러)
async def ensure_collection() -> None:
    client = get_vector_db_client()
    collection_name = settings.vector_db_collection

    # 1. 컬렉션이 없으면 새로 만들기
    if not await client.collection_exists(collection_name):
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.embedding_dim,  # 벡터 차원 (bge-m3 = 1024)
                # 코사인 유사도: 두 벡터의 "방향"이 얼마나 비슷한지로 문장 의미의 유사도를 계산
                #  (bge-m3 같은 문장 임베딩 모델에서 가장 일반적으로 쓰는 방식)
                distance=Distance.COSINE,
            ),
        )
        return

    # 2. 컬렉션이 이미 있으면 차원이 설정과 같은지 확인
    #  - 임베딩 모델을 바꾸면 벡터 차원이 달라질 수 있음 (예: 1024 -> 768)
    #  - 차원이 다른 벡터는 같은 컬렉션에 저장할 수 없으므로, 서버 시작 시점에 미리 알려줌
    collection_info = await client.get_collection(collection_name)
    existing_dim = collection_info.config.params.vectors.size
    if existing_dim != settings.embedding_dim:
        raise VectorDBError(
            f"컬렉션 '{collection_name}'의 벡터 차원({existing_dim})이 "
            f"설정값 EMBEDDING_DIM({settings.embedding_dim})과 다릅니다. "
            "임베딩 모델을 바꿨다면 새 컬렉션 이름(VECTOR_DB_COLLECTION)을 사용하세요."
        )


# Vector DB 연결 종료 함수 - src/main.py의 lifespan에서 사용
async def close_vector_db() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
