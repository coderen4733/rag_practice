# "질문 - 정답 문서" 목록으로 검색이 얼마나 정확한지 점수로 계산
#    - scripts/evaluate_search.py(평가 스크립트)에서 사용
#    - 나중에 "검색 품질 평가" 메뉴(API)를 만들 때도 이 함수를 그대로 사용
#
# 📌 평가 지표 (모두 0 ~ 1 사이, 1에 가까울수록 좋음)
#  - Hit@1     : 1등 결과가 정답 문서인 비율
#  - Recall@K  : 상위 K개 안에 정답 문서가 하나라도 있는 비율
#  - MRR       : 정답이 몇 등에 나왔는지 반영한 점수의 평균
#                (1등=1점, 2등=0.5점, 3등=0.33점 ... 없으면 0점)
#  - 키워드 Recall@K: 상위 K개 청크 원문 안에 "정답 문구"가 실제로 들어 있는 비율
#    (정답 문서를 찾았더라도 "답이 적힌 청크"를 찾았는지 한 번 더 확인)

from collections.abc import Callable
from dataclasses import dataclass

from src.core.vector_db import ChunkSearchHit


# 평가 질문 1개
@dataclass(frozen=True)
class EvalCase:
    question: str  # 검색할 질문
    expected_document: str  # 정답 문서 파일명에 포함된 글자 (예: "01_")
    expected_keyword: str | None = None  # 정답 청크에 들어 있어야 할 문구 (예: "100만 원")


# 평가 질문 1개의 결과
@dataclass(frozen=True)
class EvalCaseResult:
    case: EvalCase
    document_rank: int | None  # 정답 문서가 처음 나온 순위 (없으면 None)
    keyword_rank: int | None  # 정답 문구가 들어 있는 청크가 처음 나온 순위 (없으면 None)
    top_filenames: list[str]  # 검색 결과 파일명 목록 (결과 확인용)


# 조건에 맞는 결과가 처음 나온 순위 찾기 (1부터, 없으면 None)
#  - condition: 결과 1개를 받아서 True/False를 돌려주는 함수
def first_rank(
    hits: list[ChunkSearchHit],
    condition: Callable[[ChunkSearchHit], bool],
) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if condition(hit):
            return rank
    return None


# 평가 질문 1개 채점
def evaluate_case(case: EvalCase, hits: list[ChunkSearchHit]) -> EvalCaseResult:
    document_rank = first_rank(hits, lambda hit: case.expected_document in hit.filename)
    keyword_rank = None
    if case.expected_keyword:
        # 정답 문서의 청크이면서, 원문에 정답 문구가 들어 있는 경우
        keyword = case.expected_keyword
        keyword_rank = first_rank(
            hits,
            lambda hit: case.expected_document in hit.filename and keyword in hit.text,
        )
    return EvalCaseResult(
        case=case,
        document_rank=document_rank,
        keyword_rank=keyword_rank,
        top_filenames=[hit.filename for hit in hits],
    )


# 전체 결과 요약 (평가 지표 계산)
#  - k: Recall@K의 K (보통 검색할 때 사용한 top_k)
def summarize(results: list[EvalCaseResult], k: int) -> dict[str, float]:
    if not results:
        return {"hit_at_1": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "keyword_recall_at_k": 0.0}

    total = len(results)
    hit_at_1 = sum(1 for result in results if result.document_rank == 1) / total
    recall_at_k = (
        sum(
            1
            for result in results
            if result.document_rank is not None and result.document_rank <= k
        )
        / total
    )
    mrr = sum(1 / result.document_rank for result in results if result.document_rank) / total

    # 키워드 평가는 정답 문구가 있는 질문만 계산
    keyword_cases = [result for result in results if result.case.expected_keyword]
    keyword_recall = (
        sum(
            1
            for result in keyword_cases
            if result.keyword_rank is not None and result.keyword_rank <= k
        )
        / len(keyword_cases)
        if keyword_cases
        else 0.0
    )
    return {
        "hit_at_1": hit_at_1,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "keyword_recall_at_k": keyword_recall,
    }
