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

#  문서 청크 저장/삭제/개수 세기에 필요한 도구 추가
#    - uuid: 청크마다 고유한 포인트 id를 만들기 위함
#    - UnexpectedResponse, ResponseHandlingException: Qdrant 요청이 실패했을 때 발생하는 에러
#    - Filter, FieldCondition, MatchValue, FilterSelector: "document_id가 N인 포인트"를 고르는 조건
#    - PayloadSchemaType: payload 색인(index)의 종류, PointStruct: 저장할 포인트 1개의 형식
import uuid  # 청크마다 고유한 포인트 id 만드는 용

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.core.config import get_settings

# get_settings()를 호출하여 환경변수 객체 가져오기
settings = get_settings()

# 서버 전체에서 함께 쓰는 Qdrant 클라이언트 (init_vector_db()가 호출되기 전까지는 None)
#  - 앞에 _(언더바): "이 파일 안에서만 직접 다루는 변수"라는 파이썬의 관례
#    => 다른 파일에서는 get_vector_db_client()로 꺼내 써야 함
_client: AsyncQdrantClient | None = None

#  * Qdrant 요청 실패 시 발생하는 에러 종류 묶음 추가
#  - UnexpectedResponse       : Qdrant가 에러를 응답함 (예: 컬렉션 없음, 권한 없음)
#  - ResponseHandlingException: Qdrant에 연결 자체가 안 됨 (예: 주소 오류, 시간 초과)
#  - 이 에러들이 나면 VectorDBError로 바꿔서 던짐 => 다른 파일은 VectorDBError만 처리하면 됨
QDRANT_ERRORS = (UnexpectedResponse, ResponseHandlingException)

# 문서 id를 저장하는 payload 필드 이름 (색인 생성, 조회 조건에서 공통으로 사용)
DOCUMENT_ID_FIELD = "document_id"


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
#  - document_id 색인이 없으면 만듦
async def ensure_collection() -> None:
    client = get_vector_db_client()
    collection_name = settings.vector_db_collection

    # 1. 컬렉션이 없으면 새로 만들기
    # 컬렉션을 만든 뒤 바로 return 하지 않고 3번(색인 준비)까지 진행하도록 변경
    #  - if 컬렉션 없음: 생성 / else: 2번(차원 확인) => 두 경우 모두 3번 실행
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
    else:
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

    # 3. document_id 색인(payload index) 준비
    #  - "document_id가 N인 청크"를 빠르게 찾을 수 있도록 색인을 만듦 (없을 때만)
    #    => 문서 삭제 시 그 문서의 청크만 골라 지울 때 사용
    #    => 책 뒤의 "찾아보기(색인)"처럼, 전체를 다 뒤지지 않고 바로 찾게 해줌
    #  - Qdrant Cloud는 색인 없는 필드로 조건 검색하는 것을 막아둘 수 있으므로 꼭 필요함
    #  - payload_schema: 이 컬렉션에 이미 만들어진 색인 목록
    #  - 참고: 테스트용 메모리 Qdrant는 색인 기능이 없어서 경고만 출력하고 무시함
    collection_info = await client.get_collection(collection_name)
    if DOCUMENT_ID_FIELD not in collection_info.payload_schema:
        await client.create_payload_index(
            collection_name=collection_name,
            field_name=DOCUMENT_ID_FIELD,
            field_schema=PayloadSchemaType.INTEGER,  # document_id는 정수(int)
        )


# 청크마다 고유한 포인트 id 만들기 (이 파일 안에서만 사용)
#  - Qdrant 포인트 id는 정수 또는 UUID 형식만 가능 => 문서 id + 청크 번호로 UUID를 만듦
#  - uuid5: 같은 입력이면 "항상 같은 UUID"가 나옴 (uuid4는 매번 랜덤)
#    => 같은 문서의 같은 청크를 다시 저장하면 새로 추가되지 않고 "덮어쓰기" 됨 (중복 방지)
def _chunk_point_id(document_id: int, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"document:{document_id}:chunk:{chunk_index}"))


# "document_id가 N인 포인트"를 고르는 조건 만들기 (이 파일 안에서만 사용)
#  - SQL로 비유하면: WHERE document_id = N
def _document_filter(document_id: int) -> Filter:
    return Filter(must=[FieldCondition(key=DOCUMENT_ID_FIELD, match=MatchValue(value=document_id))])


# 문서 청크 저장 함수 추가
#  - 청크 원문 + 벡터를 Qdrant에 저장 (문서 등록 기능에서 사용)
#  - start_index: 이번에 저장하는 청크들 중 첫 번째 청크의 번호
#    => 청크를 32개씩 나눠서 저장할 때 번호가 0, 1, 2 ... 로 끝까지 이어지도록 하기 위함
#  - 각 포인트의 payload(추가 정보): 문서 id, 청크 번호, 파일명, 청크 원문
#    => 나중에 검색 결과에서 "어느 문서의 어떤 내용인지" 바로 보여줄 수 있음
async def upsert_document_chunks(
    document_id: int,
    filename: str,
    chunks: list[str],
    vectors: list[list[float]],
    start_index: int = 0,
) -> None:
    # 1. 청크 수와 벡터 수가 같은지 확인
    if len(chunks) != len(vectors):
        raise VectorDBError(f"청크 수({len(chunks)})와 벡터 수({len(vectors)})가 다릅니다.")
    # 2. 저장할 포인트 목록 만들기
    #  - zip(A, B): A와 B를 한 쌍씩 묶어서 꺼냄 => (청크1, 벡터1), (청크2, 벡터2) ...
    #  - strict=True: A와 B의 길이가 다르면 에러 (ruff B905 규칙)
    #  - enumerate: 몇 번째인지(offset)도 함께 꺼냄 => 청크 번호 = start_index + offset
    points = [
        PointStruct(
            id=_chunk_point_id(document_id, start_index + offset),
            vector=vector,
            payload={
                DOCUMENT_ID_FIELD: document_id,
                "chunk_index": start_index + offset,
                "filename": filename,
                "text": chunk,
            },
        )
        for offset, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    # 3. Qdrant에 저장 (upsert: 없으면 추가, 같은 id가 있으면 덮어쓰기)
    #  - wait=True: Qdrant가 저장을 "완료"할 때까지 기다린 뒤 다음 코드 진행
    try:
        await get_vector_db_client().upsert(
            collection_name=settings.vector_db_collection,
            points=points,
            wait=True,
        )
    except QDRANT_ERRORS as err:
        raise VectorDBError(f"Vector DB에 청크를 저장하지 못했습니다. ({err})") from err


# 문서 청크 전체 삭제 함수 추가
#  - 특정 문서(document_id)의 청크를 Qdrant에서 모두 삭제 (문서 삭제 기능에서 사용)
async def delete_document_chunks(document_id: int) -> None:
    try:
        await get_vector_db_client().delete(
            collection_name=settings.vector_db_collection,
            # FilterSelector: 포인트 id 목록 대신 "조건"으로 삭제할 포인트를 고름
            points_selector=FilterSelector(filter=_document_filter(document_id)),
            wait=True,
        )
    except QDRANT_ERRORS as err:
        raise VectorDBError(f"Vector DB에서 청크를 삭제하지 못했습니다. ({err})") from err


# 문서 청크 개수 세기 함수 추가
#  - 특정 문서(document_id)의 청크가 Qdrant에 몇 개 저장되어 있는지 확인
#    (DB의 chunk_count와 실제 저장 개수가 같은지 확인할 때 사용)
async def count_document_chunks(document_id: int) -> int:
    try:
        result = await get_vector_db_client().count(
            collection_name=settings.vector_db_collection,
            count_filter=_document_filter(document_id),
            exact=True,  # 대략적인 값이 아니라 정확한 개수
        )
    except QDRANT_ERRORS as err:
        raise VectorDBError(f"Vector DB에서 청크 개수를 세지 못했습니다. ({err})") from err
    return result.count


# Vector DB 연결 종료 함수 - src/main.py의 lifespan에서 사용
async def close_vector_db() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
