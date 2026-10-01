#  * 챗봇(Chat) API 테스트
#  - 질문 -> 문서 검색 -> 프롬프트 조립 -> LLM 답변 흐름, 스트리밍, 상태 확인, 장애 상황 확인
#  - 실제 서버 대신 사용하는 것 (conftest.py의 fixture)
#    - 메모리 Qdrant + 가짜 임베딩 (rag_env), 가짜 LLM (fake_llm)
#  - 실제 답변 품질은 scripts/evaluate_chat.py 로 실제 LLM을 사용해서 확인
#  - 대화 이어가기 + 대화 이력 테스트 (5~8번)

import json
from unittest.mock import AsyncMock

import pytest

# DB 직접 확인용 import (저장된 메시지 수 세기)
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from src.core import llm
from src.services.iam.user.enums import UserRole

# 대화 이어가기 관련 import
from src.services.rag.chat import repository as chat_repository
from src.services.rag.chat import service as chat_service
from src.services.rag.chat.models import ChatMessage
from src.services.rag.chat.prompt import (
    NO_SOURCE_ANSWER,
    REWRITE_ANSWER_LENGTH,
    REWRITE_PROMPT,
    SYSTEM_PROMPT,
    build_context,
    build_history,
    build_messages,
    build_rewrite_messages,
    clean_rewritten_question,
)
from src.services.rag.chat.schemas import ChatSourceRes
from src.services.rag.chat.service import LLM_ERROR_MESSAGE, SAVE_ERROR_MESSAGE
from src.services.rag.document.chunker import split_text


# ─────────────────────────────────────────────
# 이 파일에서 공통으로 쓰는 fixture / 도우미 함수
# ─────────────────────────────────────────────
@pytest.fixture
async def admin(make_user):
    return await make_user("admin@corp.com", role=UserRole.ADMIN)


@pytest.fixture
async def normal_user(make_user):
    return await make_user("user@corp.com", role=UserRole.USER)


# 테스트용 문서 내용 (청크가 여러 개로 나뉘도록 길게)
def long_text(prefix="휴가", sentence_count=100):
    sentences = [
        f"{prefix} {number}번 규정은 중요한 내용입니다." for number in range(sentence_count)
    ]
    return " ".join(sentences)


# 문서 업로드 도우미 (청크 목록을 돌려줌)
async def upload(client, headers, filename="휴가규정.md", text=None):
    text = text or long_text()
    response = await client.post(
        "/documents/", files={"file": (filename, text.encode(), "text/plain")}, headers=headers
    )
    assert response.status_code == 201
    return split_text(text, chunk_size=500, chunk_overlap=100)


# SSE(스트리밍) 응답 본문 해석 => [(이벤트 이름, 데이터), ...]
#  - 본문 예: "event: token\ndata: {\"text\": \"안\"}\n\nevent: done\ndata: {...}\n\n"
def parse_sse(body: str) -> list[tuple[str, object]]:
    events = []
    for block in body.strip().split("\n\n"):
        event_line, data_line = block.split("\n", 1)
        events.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return events


# ─────────────────────────────────────────────
# 1. 프롬프트 조립 (단위 테스트)
# ─────────────────────────────────────────────
def make_source(number, text, filename="a.md", chunk_index=0):
    return ChatSourceRes(
        number=number,
        document_id=1,
        filename=filename,
        chunk_index=chunk_index,
        text=text,
        score=0.8,
    )


# 참고 문서 부분: [번호] 출처: 파일명 (청크 #번호) + 원문, 문서 사이는 빈 줄
def test_build_context():
    context = build_context(
        [make_source(1, "첫째 내용", chunk_index=3), make_source(2, "둘째 내용", "b.md")]
    )

    assert context == "[1] 출처: a.md (청크 #3)\n첫째 내용\n\n[2] 출처: b.md (청크 #0)\n둘째 내용"


# 메시지 목록: system(규칙) + user(참고 문서 + 질문)
def test_build_messages():
    messages = build_messages("연차는?", [make_source(1, "연차 규정")])

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1]["role"] == "user"
    assert (
        messages[1]["content"]
        == "[참고 문서]\n[1] 출처: a.md (청크 #0)\n연차 규정\n\n[질문]\n연차는?"
    )


# ─────────────────────────────────────────────
# 2. 챗봇 답변 (POST /chat/) - 한 번에 받기
# ─────────────────────────────────────────────
# 답변 성공 => 검색된 청크가 프롬프트에 들어가고, 답변 + 출처를 돌려줌 (일반 사용자도 가능)
async def test_chat_success(client, admin, normal_user, auth_header, rag_env, fake_llm):
    chunks = await upload(client, auth_header(admin))
    fake_llm.answer = "휴가 규정은 중요합니다. [1]"

    # 청크 원문을 그대로 질문 => 가짜 임베딩 특성상 그 청크가 1등으로 검색됨
    response = await client.post(
        "/chat/", json={"question": chunks[2]}, headers=auth_header(normal_user)
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"] == "휴가 규정은 중요합니다. [1]"
    assert data["model"] == "test-model"
    assert len(data["sources"]) == 5  # CHAT_TOP_K 기본값
    assert data["sources"][0]["number"] == 1
    assert data["sources"][0]["text"] == chunks[2]
    assert data["sources"][0]["chunk_index"] == 2
    # LLM에게 보낸 프롬프트: 규칙 + 1등 청크(출처 표시 포함) + 질문
    messages = fake_llm.calls[0]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert f"[1] 출처: 휴가규정.md (청크 #2)\n{chunks[2]}" in messages[1]["content"]
    assert messages[1]["content"].endswith(f"[질문]\n{chunks[2]}")


# top_k를 보내면 => 그 개수만큼만 근거로 사용
async def test_chat_custom_top_k(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))

    response = await client.post(
        "/chat/", json={"question": "질문", "top_k": 2}, headers=auth_header(admin)
    )

    assert len(response.json()["data"]["sources"]) == 2
    assert "[3]" not in fake_llm.calls[0][1]["content"]


# 등록된 문서가 없으면 => LLM을 호출하지 않고 "찾을 수 없음" 안내 (지어내기 원천 차단)
async def test_chat_no_documents(client, admin, auth_header, rag_env, fake_llm):
    response = await client.post("/chat/", json={"question": "연차는?"}, headers=auth_header(admin))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"] == NO_SOURCE_ANSWER
    assert data["sources"] == []
    assert fake_llm.calls == []  # LLM을 호출하지 않았어야 함


# LLM 장애 => 503 + 내부 정보 없는 메시지
async def test_chat_llm_failure(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    fake_llm.fail = True

    response = await client.post("/chat/", json={"question": "질문"}, headers=auth_header(admin))

    assert response.status_code == 503
    assert response.json()["detail"] == LLM_ERROR_MESSAGE


# 검색(임베딩) 장애 => 503 (LLM은 호출하지 않음)
async def test_chat_search_failure(client, admin, auth_header, rag_env, fake_llm):
    rag_env.fail_after = 0  # 임베딩 서버 장애

    response = await client.post("/chat/", json={"question": "질문"}, headers=auth_header(admin))

    assert response.status_code == 503
    assert fake_llm.calls == []


# 로그인 필요 (401) / 잘못된 입력값 (422)
async def test_chat_without_token(client, rag_env, fake_llm):
    assert (await client.post("/chat/", json={"question": "질문"})).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},  # 질문 없음
        {"question": "   "},  # 공백만 있는 질문
        {"question": "가" * 1001},  # 1000자 초과
        {"question": "질문", "top_k": 0},
        {"question": "질문", "top_k": 21},
    ],
)
async def test_chat_invalid_body(client, admin, auth_header, rag_env, fake_llm, body):
    response = await client.post("/chat/", json=body, headers=auth_header(admin))
    assert response.status_code == 422


# ─────────────────────────────────────────────
# 3. 챗봇 답변 (POST /chat/stream) - 스트리밍
# ─────────────────────────────────────────────
# 이벤트 순서: sources(출처) -> token(답변 조각 여러 번) -> done(끝)
async def test_chat_stream_success(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    fake_llm.answer = "연차는 3근무일 전에 신청합니다. [1]"

    response = await client.post(
        "/chat/stream", json={"question": "연차 신청"}, headers=auth_header(admin)
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"token"}
    assert len(events[0][1]) == 5  # 출처 5개
    # 답변 조각을 모두 합치면 원래 답변이 되어야 함
    assert "".join(data["text"] for name, data in events if name == "token") == fake_llm.answer
    assert events[-1][1]["model"] == "test-model"


# 등록된 문서가 없으면 => 빈 출처 + "찾을 수 없음" 안내 + done (LLM 호출 없음)
async def test_chat_stream_no_documents(client, admin, auth_header, rag_env, fake_llm):
    response = await client.post(
        "/chat/stream", json={"question": "질문"}, headers=auth_header(admin)
    )

    events = parse_sse(response.text)
    assert events[0] == ("sources", [])
    assert events[1] == ("token", {"text": NO_SOURCE_ANSWER})
    assert events[2][0] == "done"
    assert fake_llm.calls == []


# LLM 장애 (시작하자마자) => 출처는 보낸 뒤 error 이벤트로 알림 (done 없음)
async def test_chat_stream_llm_failure(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    fake_llm.fail = True

    response = await client.post(
        "/chat/stream", json={"question": "질문"}, headers=auth_header(admin)
    )

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources", "error"]
    assert events[-1][1] == {"message": LLM_ERROR_MESSAGE}


# LLM 장애 (답변 도중) => 받은 조각까지 보낸 뒤 error 이벤트
async def test_chat_stream_llm_failure_midway(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    fake_llm.answer = "하나 둘 셋 넷"
    fake_llm.fail_after_pieces = 2  # "하나 ", "둘 " 까지만 보내고 장애

    response = await client.post(
        "/chat/stream", json={"question": "질문"}, headers=auth_header(admin)
    )

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["sources", "token", "token", "error"]


# 검색(임베딩) 장애 => 스트리밍을 시작하기 전이므로 일반 503 응답
async def test_chat_stream_search_failure(client, admin, auth_header, rag_env, fake_llm):
    rag_env.fail_after = 0

    response = await client.post(
        "/chat/stream", json={"question": "질문"}, headers=auth_header(admin)
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "임베딩 서버에 문제가 있어 검색하지 못했습니다."


# 로그인 필요 (401)
async def test_chat_stream_without_token(client, rag_env, fake_llm):
    assert (await client.post("/chat/stream", json={"question": "질문"})).status_code == 401


# ─────────────────────────────────────────────
# 4. LLM 연결 상태 (GET /chat/status)
# ─────────────────────────────────────────────
# 연결 정상 => available: true
async def test_chat_status_available(client, normal_user, auth_header, monkeypatch):
    monkeypatch.setattr(llm, "check_llm_connection", AsyncMock())

    response = await client.get("/chat/status", headers=auth_header(normal_user))

    assert response.status_code == 200
    assert response.json()["data"] == {"model": "test-model", "available": True, "message": None}


# 연결 실패 => available: false + 이유
async def test_chat_status_unavailable(client, normal_user, auth_header, monkeypatch):
    monkeypatch.setattr(
        llm, "check_llm_connection", AsyncMock(side_effect=llm.LLMError("모델 없음"))
    )

    response = await client.get("/chat/status", headers=auth_header(normal_user))

    data = response.json()["data"]
    assert data["available"] is False
    assert data["message"] == "모델 없음"


# 로그인 필요 (401)
async def test_chat_status_without_token(client):
    assert (await client.get("/chat/status")).status_code == 401


# ─────────────────────────────────────────────
# 5. 대화 이어가기 - 프롬프트 조립 (단위 테스트)
# ─────────────────────────────────────────────
# 이전 대화 정리: 답변의 출처 번호 [1]은 지우고, 질문은 그대로
def test_build_history():
    history = build_history(
        [("user", "연차는 며칠이야? [1]"), ("assistant", "연차는 15일입니다. [1][2]")]
    )

    assert history == [
        {"role": "user", "content": "연차는 며칠이야? [1]"},  # 질문은 손대지 않음
        {"role": "assistant", "content": "연차는 15일입니다."},
    ]


# 이전 대화 + 다시 쓴 질문 => system + 이전 대화 + (참고 문서 + 질문 + 다시 쓴 질문)
def test_build_messages_with_history():
    history = [
        {"role": "user", "content": "연차는 며칠이야?"},
        {"role": "assistant", "content": "15일입니다."},
    ]

    messages = build_messages(
        "그럼 신입사원은?", [make_source(1, "연차 규정")], history, "신입사원의 연차는?"
    )

    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1:3] == history
    assert messages[3]["content"].endswith(
        "[질문]\n그럼 신입사원은?\n(이전 대화를 반영한 질문: 신입사원의 연차는?)"
    )


# 다시 쓴 질문이 원래 질문과 같으면 => 기존과 똑같은 메시지 (중복 표시 없음)
def test_build_messages_same_search_query():
    sources = [make_source(1, "연차 규정")]

    assert build_messages("연차는?", sources, [], "연차는?") == build_messages("연차는?", sources)


# 질문 다시 쓰기 요청: 규칙 + [이전 대화] + [새 질문], 긴 답변은 앞부분만
def test_build_rewrite_messages():
    long_answer = "가" * (REWRITE_ANSWER_LENGTH + 10)
    history = [
        {"role": "user", "content": "연차는 며칠이야?"},
        {"role": "assistant", "content": long_answer},
    ]

    messages = build_rewrite_messages("그럼 신입사원은?", history)

    assert messages[0] == {"role": "system", "content": REWRITE_PROMPT}
    expected_answer = "가" * REWRITE_ANSWER_LENGTH + "…"
    assert messages[1]["content"] == (
        f"[이전 대화]\n사용자: 연차는 며칠이야?\nAI: {expected_answer}"
        "\n\n[새 질문]\n그럼 신입사원은?"
    )


# LLM이 다시 쓴 질문 정리 (이름표, 따옴표, 설명 줄 제거 / 이상하면 원래 질문 사용)
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("신입사원의 연차는 며칠인가?", "신입사원의 연차는 며칠인가?"),
        ("  다시 쓴 질문: 신입사원의 연차는?  ", "신입사원의 연차는?"),
        ('"신입사원의 연차는?"', "신입사원의 연차는?"),
        ("\n신입사원의 연차는?\n설명: 이전 대화에서 연차를 찾음", "신입사원의 연차는?"),
        ("", "원래 질문"),  # 빈 응답
        ('""', "원래 질문"),  # 따옴표만
        ("가" * 1001, "원래 질문"),  # 너무 김 (질문에 답해버린 경우 등)
        ("원래  질 문", "원래 질문"),  # 띄어쓰기만 다름 (예: "2031년" => "2031 년")
    ],
)
def test_clean_rewritten_question(text, expected):
    assert clean_rewritten_question(text, fallback="원래 질문") == expected


# ─────────────────────────────────────────────
# 6. 대화 저장 + 이어서 질문하기
# ─────────────────────────────────────────────
# 스트리밍으로 질문하기 도우미 => SSE 이벤트 목록
async def ask_stream(client, headers, question, conversation_id=None):
    body = {"question": question}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    response = await client.post("/chat/stream", json=body, headers=headers)
    assert response.status_code == 200
    return parse_sse(response.text)


# DB에 저장된 메시지 수 세기 도우미
async def count_messages(session_factory):
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(ChatMessage))


# 첫 질문 (스트리밍) => 대화방이 새로 만들어지고, done 이벤트로 대화방 정보를 알려줌
async def test_chat_stream_creates_conversation(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    fake_llm.answer = "연차는 15일입니다. [1]"

    events = await ask_stream(client, auth_header(admin), "연차는 며칠이야?")

    done = events[-1]
    assert done[0] == "done"
    assert done[1]["conversation_title"] == "연차는 며칠이야?"  # 첫 질문이 제목
    assert done[1]["search_query"] == "연차는 며칠이야?"  # 첫 질문은 다시 쓰지 않음
    assert fake_llm.rewrite_calls == []
    # 저장된 대화 확인: 질문 1개 + 답변 1개 (답변에는 근거 문서 5개, 모델 이름)
    response = await client.get(
        f"/chat/conversations/{done[1]['conversation_id']}", headers=auth_header(admin)
    )
    assert response.status_code == 200
    messages = response.json()["data"]["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "연차는 며칠이야?"
    assert messages[0]["search_query"] == "연차는 며칠이야?"
    assert messages[1]["content"] == "연차는 15일입니다. [1]"
    assert messages[1]["model"] == "test-model"
    assert len(messages[1]["sources"]) == 5
    assert messages[1]["sources"][0] == events[0][1][0]  # 화면에 보낸 근거와 같음


# 첫 질문 (한 번에 받기) => 응답에 대화방 정보 포함, 질문/답변 저장
async def test_chat_creates_conversation(
    client, admin, auth_header, rag_env, fake_llm, session_factory
):
    await upload(client, auth_header(admin))

    response = await client.post(
        "/chat/", json={"question": "연차는 며칠이야?"}, headers=auth_header(admin)
    )

    data = response.json()["data"]
    assert data["conversation_id"] >= 1
    assert data["conversation_title"] == "연차는 며칠이야?"
    assert data["search_query"] == "연차는 며칠이야?"
    assert await count_messages(session_factory) == 2


# 긴 첫 질문 => 제목은 앞 50자 + "…"
async def test_chat_long_question_title(client, admin, auth_header, rag_env, fake_llm):
    question = "가" * 60

    events = await ask_stream(client, auth_header(admin), question)

    assert events[-1][1]["conversation_title"] == "가" * 50 + "…"


# 이어서 질문 => 질문을 다시 써서 검색하고, LLM에게 이전 대화를 함께 보냄
async def test_chat_follow_up_question(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    fake_llm.answer = "연차는 15일입니다. [1]"
    first = await ask_stream(client, auth_header(admin), "연차는 며칠이야?")
    conversation_id = first[-1][1]["conversation_id"]
    fake_llm.answer = "신입사원은 11일입니다. [2]"
    fake_llm.rewritten = "신입사원의 연차는 며칠인가?"

    events = await ask_stream(client, auth_header(admin), "그럼 신입사원은?", conversation_id)

    # 1. 같은 대화방에 이어서 저장, 검색에는 다시 쓴 질문 사용
    done = events[-1][1]
    assert done["conversation_id"] == conversation_id
    assert done["search_query"] == "신입사원의 연차는 며칠인가?"
    assert rag_env.calls[-1] == ["신입사원의 연차는 며칠인가?"]
    # 2. 질문 다시 쓰기 요청: 이전 대화(출처 번호는 지움) + 새 질문
    rewrite_content = fake_llm.rewrite_calls[0][1]["content"]
    assert "사용자: 연차는 며칠이야?\nAI: 연차는 15일입니다." in rewrite_content
    assert rewrite_content.endswith("[새 질문]\n그럼 신입사원은?")
    # 3. 답변 요청: system + 이전 대화(질문, 답변) + 참고 문서와 새 질문
    messages = fake_llm.calls[-1]
    assert messages[1] == {"role": "user", "content": "연차는 며칠이야?"}
    assert messages[2] == {"role": "assistant", "content": "연차는 15일입니다."}
    assert messages[3]["content"].endswith(
        "[질문]\n그럼 신입사원은?\n(이전 대화를 반영한 질문: 신입사원의 연차는 며칠인가?)"
    )
    # 4. 대화방에는 질문/답변 4개가 순서대로 저장됨
    response = await client.get(
        f"/chat/conversations/{conversation_id}", headers=auth_header(admin)
    )
    contents = [message["content"] for message in response.json()["data"]["messages"]]
    assert contents == [
        "연차는 며칠이야?",
        "연차는 15일입니다. [1]",
        "그럼 신입사원은?",
        "신입사원은 11일입니다. [2]",
    ]


# 이전 대화는 최근 N개(CHAT_HISTORY_MESSAGES)만 LLM에게 보냄
async def test_chat_history_limit(client, admin, auth_header, rag_env, fake_llm, monkeypatch):
    monkeypatch.setattr(chat_service.settings, "chat_history_messages", 2)
    await upload(client, auth_header(admin))
    first = await ask_stream(client, auth_header(admin), "질문1")
    conversation_id = first[-1][1]["conversation_id"]
    await ask_stream(client, auth_header(admin), "질문2", conversation_id)

    await ask_stream(client, auth_header(admin), "질문3", conversation_id)

    # system + 최근 2개(질문2, 답변2) + 새 질문 => 총 4개
    messages = fake_llm.calls[-1]
    assert len(messages) == 4
    assert messages[1] == {"role": "user", "content": "질문2"}


# 질문 다시 쓰기 끄기(CHAT_QUERY_REWRITE=false) => 원래 질문으로 검색 (이전 대화는 그대로 보냄)
async def test_chat_rewrite_disabled(client, admin, auth_header, rag_env, fake_llm, monkeypatch):
    monkeypatch.setattr(chat_service.settings, "chat_query_rewrite", False)
    await upload(client, auth_header(admin))
    first = await ask_stream(client, auth_header(admin), "연차는 며칠이야?")

    events = await ask_stream(
        client, auth_header(admin), "그럼 신입사원은?", first[-1][1]["conversation_id"]
    )

    assert fake_llm.rewrite_calls == []
    assert events[-1][1]["search_query"] == "그럼 신입사원은?"
    assert len(fake_llm.calls[-1]) == 4  # system + 이전 대화 2개 + 새 질문


# 질문 다시 쓰기 실패 => 답변은 실패시키지 않고 원래 질문으로 검색
async def test_chat_rewrite_failure(client, admin, auth_header, rag_env, fake_llm):
    await upload(client, auth_header(admin))
    first = await ask_stream(client, auth_header(admin), "연차는 며칠이야?")
    fake_llm.rewrite_fail = True

    events = await ask_stream(
        client, auth_header(admin), "그럼 신입사원은?", first[-1][1]["conversation_id"]
    )

    assert events[-1][0] == "done"
    assert events[-1][1]["search_query"] == "그럼 신입사원은?"
    assert rag_env.calls[-1] == ["그럼 신입사원은?"]


# 근거 문서가 없어 "찾을 수 없음"으로 답한 경우도 저장
async def test_chat_no_documents_saved(client, admin, auth_header, rag_env, fake_llm):
    events = await ask_stream(client, auth_header(admin), "연차는?")

    response = await client.get(
        f"/chat/conversations/{events[-1][1]['conversation_id']}", headers=auth_header(admin)
    )
    messages = response.json()["data"]["messages"]
    assert messages[1]["content"] == NO_SOURCE_ANSWER
    assert messages[1]["sources"] == []


# LLM 장애 (스트리밍 도중) => 질문/답변 모두 저장하지 않음 (대화방도 만들지 않음)
async def test_chat_stream_failure_not_saved(
    client, admin, auth_header, rag_env, fake_llm, session_factory
):
    await upload(client, auth_header(admin))
    fake_llm.fail_after_pieces = 1

    events = await ask_stream(client, auth_header(admin), "질문")

    assert events[-1][0] == "error"
    assert await count_messages(session_factory) == 0
    response = await client.get("/chat/conversations", headers=auth_header(admin))
    assert response.json()["data"]["total"] == 0


# LLM 장애 (한 번에 받기) => 503 + 저장하지 않음
async def test_chat_failure_not_saved(
    client, admin, auth_header, rag_env, fake_llm, session_factory
):
    await upload(client, auth_header(admin))
    fake_llm.fail = True

    response = await client.post("/chat/", json={"question": "질문"}, headers=auth_header(admin))

    assert response.status_code == 503
    assert await count_messages(session_factory) == 0


# 대화 저장 실패 (DB 장애) => 답변 조각은 보낸 뒤 error 이벤트로 "저장 실패" 알림
async def test_chat_stream_save_failure(client, admin, auth_header, rag_env, fake_llm, monkeypatch):
    await upload(client, auth_header(admin))
    monkeypatch.setattr(
        chat_repository, "create_messages", AsyncMock(side_effect=SQLAlchemyError("DB 장애"))
    )

    events = await ask_stream(client, auth_header(admin), "질문")

    names = [name for name, _ in events]
    assert names[0] == "sources"
    assert "token" in names
    assert events[-1] == ("error", {"message": SAVE_ERROR_MESSAGE})


# 없는 대화방 / 다른 사람의 대화방으로 질문 => 404 (LLM 호출 없음)
async def test_chat_other_users_conversation(
    client, admin, normal_user, auth_header, rag_env, fake_llm
):
    first = await ask_stream(client, auth_header(admin), "관리자의 질문")
    admin_conversation_id = first[-1][1]["conversation_id"]
    fake_llm.calls.clear()

    for conversation_id in [admin_conversation_id, 9999]:
        body = {"question": "질문", "conversation_id": conversation_id}
        for url in ["/chat/", "/chat/stream"]:
            response = await client.post(url, json=body, headers=auth_header(normal_user))
            assert response.status_code == 404
            assert response.json()["detail"] == "존재하지 않는 대화방입니다."
    assert fake_llm.calls == []


# ─────────────────────────────────────────────
# 7. 대화방 목록 (GET /chat/conversations)
# ─────────────────────────────────────────────
# 내 대화방만, 최근에 대화한 순서로 (이어서 질문한 대화방이 맨 위로 올라감)
async def test_conversations_list(client, admin, normal_user, auth_header, rag_env, fake_llm):
    first = await ask_stream(client, auth_header(admin), "첫 번째 대화")
    await ask_stream(client, auth_header(admin), "두 번째 대화")
    await ask_stream(client, auth_header(normal_user), "다른 사람의 대화")
    # 첫 번째 대화방에 이어서 질문 => 맨 위로
    await ask_stream(client, auth_header(admin), "이어서", first[-1][1]["conversation_id"])

    response = await client.get("/chat/conversations", headers=auth_header(admin))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2  # 다른 사람의 대화방은 보이지 않음
    assert [item["title"] for item in data["items"]] == ["첫 번째 대화", "두 번째 대화"]


# 페이지네이션 (size=2, 3개 => 2페이지)
async def test_conversations_list_pagination(client, admin, auth_header, rag_env, fake_llm):
    for number in range(3):
        await ask_stream(client, auth_header(admin), f"대화 {number}")

    response = await client.get("/chat/conversations?page=2&size=2", headers=auth_header(admin))

    data = response.json()["data"]
    assert data["total"] == 3
    assert data["total_pages"] == 2
    assert [item["title"] for item in data["items"]] == ["대화 0"]  # 가장 오래된 대화


# ─────────────────────────────────────────────
# 8. 대화방 열기 / 제목 변경 / 삭제
# ─────────────────────────────────────────────
# 제목 변경 (앞뒤 공백 제거)
async def test_update_conversation_title(client, admin, auth_header, rag_env, fake_llm):
    events = await ask_stream(client, auth_header(admin), "질문")
    conversation_id = events[-1][1]["conversation_id"]

    response = await client.patch(
        f"/chat/conversations/{conversation_id}",
        json={"title": "  연차 문의  "},
        headers=auth_header(admin),
    )

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "연차 문의"
    detail = await client.get(f"/chat/conversations/{conversation_id}", headers=auth_header(admin))
    assert detail.json()["data"]["title"] == "연차 문의"


# 잘못된 제목 => 422
@pytest.mark.parametrize("title", ["", "   ", "가" * 101])
async def test_update_conversation_invalid_title(
    client, admin, auth_header, rag_env, fake_llm, title
):
    events = await ask_stream(client, auth_header(admin), "질문")

    response = await client.patch(
        f"/chat/conversations/{events[-1][1]['conversation_id']}",
        json={"title": title},
        headers=auth_header(admin),
    )

    assert response.status_code == 422


# 삭제 => 대화방과 그 안의 메시지가 함께 삭제됨
async def test_delete_conversation(client, admin, auth_header, rag_env, fake_llm, session_factory):
    events = await ask_stream(client, auth_header(admin), "질문")
    conversation_id = events[-1][1]["conversation_id"]

    response = await client.delete(
        f"/chat/conversations/{conversation_id}", headers=auth_header(admin)
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"success": True, "id": conversation_id}
    assert await count_messages(session_factory) == 0  # 메시지도 함께 삭제
    detail = await client.get(f"/chat/conversations/{conversation_id}", headers=auth_header(admin))
    assert detail.status_code == 404


# 다른 사람의 대화방 / 없는 대화방 => 열기, 제목 변경, 삭제 모두 404
async def test_other_users_conversation_not_found(
    client, admin, normal_user, auth_header, rag_env, fake_llm
):
    events = await ask_stream(client, auth_header(admin), "관리자의 질문")
    admin_conversation_id = events[-1][1]["conversation_id"]
    headers = auth_header(normal_user)

    for conversation_id in [admin_conversation_id, 9999]:
        url = f"/chat/conversations/{conversation_id}"
        assert (await client.get(url, headers=headers)).status_code == 404
        response = await client.patch(url, json={"title": "새 제목"}, headers=headers)
        assert response.status_code == 404
        assert (await client.delete(url, headers=headers)).status_code == 404
    # 관리자의 대화방은 그대로 남아 있음
    response = await client.get(
        f"/chat/conversations/{admin_conversation_id}", headers=auth_header(admin)
    )
    assert response.status_code == 200


# 로그인 필요 (401)
async def test_conversations_without_token(client):
    assert (await client.get("/chat/conversations")).status_code == 401
    assert (await client.get("/chat/conversations/1")).status_code == 401
    assert (await client.patch("/chat/conversations/1", json={"title": "a"})).status_code == 401
    assert (await client.delete("/chat/conversations/1")).status_code == 401
