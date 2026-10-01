#  * 챗봇 답변 품질 평가 스크립트
#  - 평가 질문 세트(chat_eval_set.json)로 실제 "검색 + LLM 답변"을 만들어 보고 점검
#    1) 답할 수 있는 질문: 답변에 정답 값(예: "5일", "100만")이 모두 들어 있는지
#    2) 문서에 없는 질문: 지어내지 않고 "찾을 수 없다"고 답하는지
#    3) 답변에 출처 번호([1], [2] ...)를 표시했는지, 평균 응답 시간은 얼마인지
#    => 프롬프트(prompt.py), 모델(LLM_MODEL), 청크 수(CHAT_TOP_K)를 바꾼 뒤 비교할 때 사용
#
# 📌 실행 방법 (backend 폴더에서, 임베딩 컨테이너 + Ollama 앱 + .env 설정이 준비된 상태)
#  - uv run python -m scripts.evaluate_chat              => 답변 앞부분만 출력
#  - uv run python -m scripts.evaluate_chat --full       => 답변 전체 출력
#
# 📌 주의
#  - 실제 Qdrant에 "읽기(검색)"만 하고, 데이터를 바꾸지 않음
#  - LLM 답변을 질문 수만큼 만들기 때문에 몇 분 정도 걸릴 수 있음

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

from src.core import embedding, llm, vector_db
from src.core.config import get_settings
from src.services.rag.chat.prompt import build_messages
from src.services.rag.chat.schemas import ChatSourceRes

settings = get_settings()

DEFAULT_EVAL_SET = Path(__file__).resolve().parent / "chat_eval_set.json"

# "찾을 수 없다"는 답변인지 판단하는 문구
NOT_FOUND_PATTERN = "찾을 수 없"

# 출처 번호 표시([1], [2] ...)가 있는지 확인하는 정규식
CITATION_PATTERN = re.compile(r"\[\d+\]")

# 답변에 한자(중국어)가 섞였는지 확인하는 정규식 (한중일 통합 한자 범위)
HANJA_PATTERN = re.compile(r"[一-鿿]")


# 질문 하나에 대해 "검색 -> 프롬프트 -> LLM 답변"을 실행 (실제 챗봇 API와 같은 흐름)
#  - 반환값: (답변, 걸린 시간(초))
async def ask(question: str) -> tuple[str, float]:
    started_at = time.perf_counter()
    query_vector = await embedding.embed_text(question)
    hits = await vector_db.search_document_chunks(query_vector, limit=settings.chat_top_k)
    sources = [
        ChatSourceRes(
            number=rank,
            document_id=hit.document_id,
            filename=hit.filename,
            chunk_index=hit.chunk_index,
            text=hit.text,
            score=hit.score,
        )
        for rank, hit in enumerate(hits, start=1)
    ]
    answer = await llm.chat_completion(build_messages(question, sources))
    return answer.strip(), time.perf_counter() - started_at


# 정답 값이 답변에 들어 있는지 확인
#  - "4회|4번" 처럼 | 로 나눈 값은 그중 하나만 있으면 통과
#  - 띄어쓰기는 무시하고 비교 (모델이 "32 일", "6 조 2 천억"처럼 띄어 써도 정답으로 인정)
def has_keyword(answer: str, keyword: str) -> bool:
    compact_answer = "".join(answer.split())  # split(): 모든 공백/줄바꿈 기준으로 나눔
    return any("".join(option.split()) in compact_answer for option in keyword.split("|"))


# 답변을 한 줄로 줄여서 보여주기 (--full 이 아니면 앞부분만)
def preview(answer: str, full: bool) -> str:
    one_line = answer.replace("\n", " / ")
    return one_line if full or len(one_line) <= 120 else f"{one_line[:120]}…"


async def main(eval_set: Path, full: bool) -> None:
    data = json.loads(eval_set.read_text(encoding="utf-8"))

    # 1. 서버가 시작할 때와 똑같이 클라이언트 준비
    vector_db.init_vector_db()
    embedding.init_embedding()
    llm.init_llm()
    try:
        print(
            f"\n🤖 챗봇 답변 평가 (모델: {settings.llm_model}, "
            f"근거 청크: {settings.chat_top_k}개)\n"
        )
        elapsed_list: list[float] = []
        cited = 0
        answers: list[str] = []  # 모든 답변 (한자 섞임 확인용)

        # 2. 답할 수 있는 질문 => 정답 값이 모두 들어 있어야 통과
        print("[1] 답할 수 있는 질문 - 정답 값 포함 여부")
        correct = 0
        for number, case in enumerate(data["answerable"], start=1):
            answer, elapsed = await ask(case["question"])
            elapsed_list.append(elapsed)
            answers.append(answer)
            missing = [kw for kw in case["expected_keywords"] if not has_keyword(answer, kw)]
            passed = not missing
            correct += passed
            cited += bool(CITATION_PATTERN.search(answer))
            mark = "✅" if passed else f"❌ (빠진 값: {', '.join(missing)})"
            print(f"{number:>3}. {mark}  {elapsed:.1f}초  Q: {case['question']}")
            print(f"     A: {preview(answer, full)}")

        # 3. 문서에 없는 질문 => "찾을 수 없다"고 답해야 통과
        print("\n[2] 문서에 없는 질문 - 지어내지 않고 '찾을 수 없음'으로 답하는지")
        refused = 0
        for number, question in enumerate(data["unanswerable"], start=1):
            answer, elapsed = await ask(question)
            elapsed_list.append(elapsed)
            answers.append(answer)
            passed = NOT_FOUND_PATTERN in answer
            refused += passed
            print(f"{number:>3}. {'✅' if passed else '❌'}  {elapsed:.1f}초  Q: {question}")
            print(f"     A: {preview(answer, full)}")

        # 4. 요약
        answerable_total = len(data["answerable"])
        unanswerable_total = len(data["unanswerable"])
        print("\n📊 요약")
        print(f"  - 정답 값 포함   : {correct}/{answerable_total}")
        print(f"  - 지어내기 방지 : {refused}/{unanswerable_total}")
        print(f"  - 출처 번호 표시 : {cited}/{answerable_total}")
        mixed = sum(1 for answer in answers if HANJA_PATTERN.search(answer))
        print(f"  - 한자 섞인 답변 : {mixed}/{len(answers)} (0이어야 좋음)")
        average = sum(elapsed_list) / len(elapsed_list)
        print(f"  - 평균 응답 시간 : {average:.1f}초 (검색 + 답변 생성)\n")
    finally:
        await vector_db.close_vector_db()
        await embedding.close_embedding()
        await llm.close_llm()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="챗봇 답변 품질 평가")
    parser.add_argument(
        "--eval-set", type=Path, default=DEFAULT_EVAL_SET, help="평가 질문 세트 파일"
    )
    parser.add_argument("--full", action="store_true", help="답변 전체 출력")
    args = parser.parse_args()
    asyncio.run(main(args.eval_set, args.full))
