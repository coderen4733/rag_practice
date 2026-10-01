#  * 검색 품질 평가 계산 함수(evaluation.py) 테스트
#  - Hit@1, Recall@K, MRR, 키워드 Recall@K 계산이 정확한지 확인 (단위 테스트)

import pytest

from src.core.vector_db import ChunkSearchHit
from src.services.rag.search.evaluation import EvalCase, evaluate_case, first_rank, summarize


# 테스트용 검색 결과 만들기 (파일명, 원문만 의미 있음)
def hit(filename, text="", score=0.5):
    return ChunkSearchHit(document_id=1, chunk_index=0, filename=filename, text=text, score=score)


# 조건에 맞는 결과가 처음 나온 순위 (없으면 None)
def test_first_rank():
    hits = [hit("a.md"), hit("b.md"), hit("b.md")]
    assert first_rank(hits, lambda h: h.filename == "b.md") == 2
    assert first_rank(hits, lambda h: h.filename == "z.md") is None


# 정답 문서 순위와 정답 문구 순위를 따로 채점
#  - 2등은 정답 문서지만 정답 문구가 없고, 3등에 정답 문구가 있는 경우
def test_evaluate_case_document_and_keyword_rank():
    case = EvalCase(question="질문", expected_document="01_", expected_keyword="100만 원")
    hits = [
        hit("02_법률.md", "경조금 100만 원"),  # 문구는 있지만 정답 문서가 아님 => 인정 안 함
        hit("01_교육자료.md", "휴가 5일"),
        hit("01_교육자료.md", "경조금 100만 원"),
    ]

    result = evaluate_case(case, hits)

    assert result.document_rank == 2
    assert result.keyword_rank == 3
    assert result.top_filenames == ["02_법률.md", "01_교육자료.md", "01_교육자료.md"]


# 요약 지표 계산
#  - 질문 4개: 정답 문서 순위 = 1등, 2등, 5등, 없음 / K=3
def test_summarize():
    cases = [
        EvalCase(question=f"q{i}", expected_document="A", expected_keyword="k") for i in range(4)
    ]
    results = [
        evaluate_case(cases[0], [hit("A", "k")]),  # 1등 (문구 1등)
        evaluate_case(cases[1], [hit("B"), hit("A", "k")]),  # 2등 (문구 2등)
        # 5등, 문구 없음
        evaluate_case(cases[2], [hit("B"), hit("B"), hit("B"), hit("B"), hit("A")]),
        evaluate_case(cases[3], [hit("B")]),  # 없음
    ]

    summary = summarize(results, k=3)

    assert summary["hit_at_1"] == pytest.approx(1 / 4)  # 1등은 1개
    assert summary["recall_at_k"] == pytest.approx(2 / 4)  # 3등 이내는 1등, 2등 => 2개
    assert summary["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 5 + 0) / 4)
    assert summary["keyword_recall_at_k"] == pytest.approx(2 / 4)


# 결과가 없으면 모든 지표 0
def test_summarize_empty():
    assert summarize([], k=5) == {
        "hit_at_1": 0.0,
        "recall_at_k": 0.0,
        "mrr": 0.0,
        "keyword_recall_at_k": 0.0,
    }
