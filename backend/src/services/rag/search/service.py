# 📌 검색 흐름
#  1) 질문 -> 임베딩 서버(bge-m3) -> 질문 벡터 (숫자 1024개)
#  2) 질문 벡터 -> Qdrant 유사도 검색 -> 가장 비슷한 청크 top_k개
#  3) 청크 원문 + 출처(파일명, 청크 번호) + 유사도 점수를 응답
#
# 📌 키워드 검색과 다른 점
#  - 키워드 검색: "부모 사망"이라는 "글자"가 있는 문서만 찾음
#  - 의미 검색(지금 만든 것): "부모님이 돌아가시면"처럼 글자가 달라도 "뜻"이 비슷하면 찾음

import logging
import time

from fastapi import HTTPException, status

# embedding, vector_db를 "파일(모듈)째로" import => 테스트에서 가짜로 바꿔치기하기 쉬움
from src.core import embedding, vector_db
from src.services.rag.search.schemas import SearchHitRes, SearchReq, SearchRes

# __name__: 현재 파일의 모듈 이름으로 로거를 만들어, 로그가 어디서 나왔는지 표시
logger = logging.getLogger(__name__)


# 문서 검색 API
async def search_documents(dto: SearchReq) -> SearchRes:
    # time.perf_counter(): 시간 측정용 시계 (걸린 시간 = 끝난 시각 - 시작 시각)
    started_at = time.perf_counter()

    # 1. 질문 -> 벡터 (임베딩 서버 호출)
    try:
        query_vector = await embedding.embed_text(dto.query)
    except embedding.EmbeddingError as err:
        # 자세한 에러는 서버 로그에만 남기고, 사용자에게는 내부 정보 없는 메시지만 보여줌
        logger.error(f"🔴 검색 질문 임베딩 실패: {err!r}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="임베딩 서버에 문제가 있어 검색하지 못했습니다.",
        ) from err

    # 2. 질문 벡터와 비슷한 청크 찾기 (Qdrant 호출)
    #  - 같은 문서 id를 여러 번 보낸 경우 중복 제거 (set: 중복 없는 모음)
    document_ids = sorted(set(dto.document_ids)) if dto.document_ids else None
    try:
        hits = await vector_db.search_document_chunks(
            query_vector=query_vector,
            limit=dto.top_k,
            document_ids=document_ids,
        )
    except vector_db.VectorDBError as err:
        logger.error(f"🔴 Vector DB 검색 실패: {err!r}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector DB에 문제가 있어 검색하지 못했습니다.",
        ) from err

    # 3. 걸린 시간 계산 (초 -> 밀리초)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)

    # 4. 응답 만들기
    #  - enumerate(hits, start=1): 순위를 1부터 매김
    data = SearchRes(
        query=dto.query,
        top_k=dto.top_k,
        total=len(hits),
        elapsed_ms=elapsed_ms,
        results=[
            SearchHitRes(
                rank=rank,
                document_id=hit.document_id,
                filename=hit.filename,
                chunk_index=hit.chunk_index,
                text=hit.text,
                score=hit.score,
            )
            for rank, hit in enumerate(hits, start=1)
        ],
    )
    # 5. Service -> Router
    return data
