from typing import Annotated

# StringConstraints: 문자열에 규칙을 붙이는 Pydantic 도구 (앞뒤 공백 제거, 길이 제한 등)
from pydantic import BaseModel, Field, StringConstraints


# 문서 검색 - 요청(Req)
class SearchReq(BaseModel):
    # 검색할 질문
    #  - strip_whitespace=True: 앞뒤 공백을 자동으로 제거한 뒤 길이를 검사
    #    => 공백만 입력한 질문("   ")은 길이 0이 되어 422(입력값 오류)로 거절됨
    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
        Field(description="검색할 질문 (1~500자)"),
    ]
    # 가져올 청크 개수 (기본 5개, 최대 20개)
    #  - 너무 많이 가져오면 느려지고, 나중에 LLM에게 넘길 때 관련 없는 내용이 섞임
    top_k: int = Field(default=5, ge=1, le=20, description="가져올 검색 결과 수 (1~20)")
    # 검색할 문서 id 목록 (비워두면 전체 문서에서 검색)
    document_ids: list[int] | None = Field(
        default=None,
        max_length=50,
        description="특정 문서에서만 검색할 때 문서 id 목록 (최대 50개)",
    )


# 검색 결과 1개(청크 1개) - 응답(Res)
class SearchHitRes(BaseModel):
    rank: int  # 순위 (1부터, 유사도가 높은 순서)
    document_id: int  # 청크가 속한 문서 id
    filename: str  # 문서 파일명 (출처)
    chunk_index: int  # 문서 안에서 몇 번째 청크인지 (0부터)
    text: str  # 청크 원문
    score: float  # 유사도 점수 (1에 가까울수록 질문과 의미가 비슷함)


# 문서 검색 - 응답(Res)
class SearchRes(BaseModel):
    query: str  # 검색한 질문 (앞뒤 공백 제거된 값)
    top_k: int  # 요청한 결과 수
    total: int  # 실제로 찾은 결과 수 (등록된 청크가 적으면 top_k보다 적을 수 있음)
    elapsed_ms: int  # 검색에 걸린 시간 (단위: 밀리초, 1000ms = 1초)
    results: list[SearchHitRes]  # 검색 결과 (유사도 높은 순)
