#  * 검색 품질 평가 스크립트
#  - 평가 질문 세트(search_eval_set.json)로 실제 Qdrant + 임베딩 서버를 검색해서
#          검색이 얼마나 정확한지 점수(Hit@1, Recall@K, MRR 등)로 보여줌
#    => 청크 크기, 임베딩 모델 등을 바꿨을 때 "좋아졌는지 나빠졌는지"를 숫자로 비교할 수 있음
#
# 📌 실행 방법 (backend 폴더에서, 임베딩 컨테이너와 .env 설정이 준비된 상태)
#  - uv run python -m scripts.evaluate_search              => 기본값(top_k=5)으로 평가
#  - uv run python -m scripts.evaluate_search --top-k 3    => 상위 3개 기준으로 평가
#  - uv run python -m scripts.evaluate_search --verbose    => 질문별 1~3등 결과 파일명도 출력
#
# 📌 주의
#  - 실제 Qdrant에 "읽기(검색)"만 하고, 데이터를 바꾸지 않음
#  - 평가 질문은 프로젝트 최상위 md 폴더의 테스트 문서 3개가 등록되어 있다고 가정함

import argparse
import asyncio
import json
from pathlib import Path

from src.core import embedding, vector_db
from src.services.rag.search.evaluation import EvalCase, evaluate_case, summarize

# 평가 질문 세트 파일 위치 (이 스크립트와 같은 폴더)
DEFAULT_EVAL_SET = Path(__file__).resolve().parent / "search_eval_set.json"


# 평가 질문 세트 읽기
def load_cases(path: Path) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalCase(
            question=item["question"],
            expected_document=item["expected_document"],
            expected_keyword=item.get("expected_keyword"),
        )
        for item in data["cases"]
    ]


# 순위를 보기 좋게 표시 (None => "-")
def show_rank(rank: int | None) -> str:
    return f"{rank}등" if rank else "-"


async def main(top_k: int, eval_set: Path, verbose: bool) -> None:
    cases = load_cases(eval_set)

    # 1. 서버가 시작할 때와 똑같이 Qdrant, 임베딩 클라이언트 준비
    vector_db.init_vector_db()
    embedding.init_embedding()
    try:
        # 2. 질문마다 검색하고 채점
        results = []
        print(f"\n🔎 검색 품질 평가 (질문 {len(cases)}개, top_k={top_k})\n")
        print(f"{'번호':>4}  {'정답 문서':>8}  {'정답 문구':>8}  질문")
        for number, case in enumerate(cases, start=1):
            query_vector = await embedding.embed_text(case.question)
            hits = await vector_db.search_document_chunks(query_vector, limit=top_k)
            result = evaluate_case(case, hits)
            results.append(result)
            # 정답 문서를 top_k 안에서 못 찾으면 ❌ 표시
            mark = "✅" if result.document_rank else "❌"
            print(
                f"{number:>4}  {mark} {show_rank(result.document_rank):>5}  "
                f"{show_rank(result.keyword_rank):>8}  {case.question}"
            )
            if verbose:
                print(f"{'':>6}결과: {', '.join(result.top_filenames[:3])}")

        # 3. 전체 요약
        summary = summarize(results, k=top_k)
        print("\n📊 요약 (1에 가까울수록 좋음)")
        print(f"  - Hit@1            : {summary['hit_at_1']:.2f}  (1등이 정답 문서인 비율)")
        print(
            f"  - Recall@{top_k:<2}         : {summary['recall_at_k']:.2f}  "
            f"(상위 {top_k}개 안에 정답 문서가 있는 비율)"
        )
        print(f"  - MRR              : {summary['mrr']:.2f}  (정답 순위를 반영한 점수)")
        print(
            f"  - 키워드 Recall@{top_k:<2}  : {summary['keyword_recall_at_k']:.2f}  "
            f"(상위 {top_k}개 청크에 정답 문구가 있는 비율)\n"
        )
    finally:
        # 4. 연결 정리 (에러가 나도 반드시 실행)
        await vector_db.close_vector_db()
        await embedding.close_embedding()


# 이 파일을 직접 실행했을 때만 아래 코드가 동작 (다른 파일에서 import 할 때는 실행되지 않음)
if __name__ == "__main__":
    # 명령줄 옵션 읽기 (예: --top-k 3)
    parser = argparse.ArgumentParser(description="검색 품질 평가")
    parser.add_argument("--top-k", type=int, default=5, help="검색 결과 수 (기본 5)")
    parser.add_argument(
        "--eval-set", type=Path, default=DEFAULT_EVAL_SET, help="평가 질문 세트 파일"
    )
    parser.add_argument("--verbose", action="store_true", help="질문별 검색 결과 파일명 출력")
    args = parser.parse_args()
    # asyncio.run(): 일반 코드에서 비동기 함수(main)를 실행
    asyncio.run(main(args.top_k, args.eval_set, args.verbose))
