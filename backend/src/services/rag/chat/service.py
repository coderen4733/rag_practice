# 📌 RAG 답변 흐름
#  1) 질문으로 문서 검색 (③ 검색 기능 재사용) => 관련 청크 top_k개 (= 출처)
#  2) 규칙 + 출처 + 질문으로 프롬프트 조립 (prompt.py)
#  3) LLM이 출처를 근거로 답변 생성 (core/llm.py)
#  4) 답변 + 출처를 함께 응답 (사용자가 답변의 근거를 직접 확인할 수 있도록)
#
# 📌 대화 이어가기 + 대화 이력 흐름
#  0) 대화방 id(conversation_id)가 오면 그 대화방의 최근 대화를 불러옴 (내 대화방만 가능)
#  1) 이전 대화가 있으면 질문을 "혼자서도 뜻이 통하는 질문"으로 다시 써서 검색
#     (예: "그럼 신입사원은?" => "신입사원의 연차는 며칠인가?")
#  2~3) LLM에게 이전 대화도 함께 보내서 답변 생성
#  5) 답변이 끝까지 완성되면 질문 + 답변을 대화방에 저장 (대화방이 없으면 새로 만듦)
#     - LLM 장애로 실패했거나, 사용자가 "중지"한 질문은 저장하지 않음
#       => 대화 이력에는 항상 "질문 + 완성된 답변" 쌍만 남음

import json
import logging
import math
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# llm을 "파일(모듈)째로" import => 테스트에서 가짜 LLM으로 바꿔치기하기 쉬움
from src.core import llm
from src.core.config import get_settings
from src.services.iam.user.models import User
from src.services.rag.chat import repository as chat_repository
from src.services.rag.chat.enums import ChatMessageRole
from src.services.rag.chat.models import ChatMessage, Conversation
from src.services.rag.chat.prompt import (
    NO_SOURCE_ANSWER,
    build_history,
    build_messages,
    build_rewrite_messages,
    clean_rewritten_question,
)
from src.services.rag.chat.schemas import (
    ChatMessageRes,
    ChatReq,
    ChatRes,
    ChatSourceRes,
    ChatStatusRes,
    ConversationDeleteRes,
    ConversationDetailRes,
    ConversationReadListQuery,
    ConversationReadListRes,
    ConversationRes,
    ConversationUpdateReq,
)
from src.services.rag.search import service as search_service
from src.services.rag.search.schemas import SearchReq

logger = logging.getLogger(__name__)

settings = get_settings()

# LLM 장애 시 사용자에게 보여줄 메시지 (서버 주소 등 내부 정보는 로그에만 남김)
LLM_ERROR_MESSAGE = "LLM 서버에 문제가 있어 답변을 만들지 못했습니다."
# 대화 저장 실패 시 사용자에게 보여줄 메시지
SAVE_ERROR_MESSAGE = "답변은 만들었지만 대화 기록을 저장하지 못했습니다."
# 새 대화방 제목 길이 (첫 질문의 앞부분을 제목으로 사용)
TITLE_LENGTH = 50


# 답변 준비 결과 (이 파일 안에서만 사용)
#  - 답변을 만들기 "전"에 준비한 값들을 한 묶음으로 전달하기 위한 상자
#  - @dataclass: 값을 담기만 하는 클래스를 간단하게 만들어 주는 도구
#    (__init__ 등을 직접 쓰지 않아도 아래 변수들을 받는 클래스가 자동으로 만들어짐)
@dataclass
class _ChatContext:
    conversation: Conversation | None  # 이어서 질문하는 대화방 (새 대화면 None)
    history: list[dict[str, str]]  # LLM에게 보낼 이전 대화 (새 대화면 빈 목록)
    search_query: str  # 검색에 사용한 질문 (다시 쓰지 않았으면 원래 질문)
    sources: list[ChatSourceRes]  # 근거 문서


# 1. 근거 문서(출처) 찾기 - 문서 검색 기능 재사용
#  - 임베딩 서버나 Vector DB 장애 시 검색 기능이 503 에러를 던짐 => 그대로 사용자에게 전달
#  * 검색어를 따로 받도록 변경
#  - search_query(이어서 묻는 질문이면 다시 쓴 질문)로 검색
async def _retrieve_sources(dto: ChatReq, search_query: str) -> list[ChatSourceRes]:
    search_result = await search_service.search_documents(
        SearchReq(
            query=search_query,
            # top_k를 보내지 않았으면 서버 설정값(CHAT_TOP_K) 사용
            top_k=dto.top_k or settings.chat_top_k,
            document_ids=dto.document_ids,
        )
    )
    # 검색 결과 순위(rank)를 그대로 출처 번호로 사용 => 답변의 [1]이 1등 청크
    return [
        ChatSourceRes(
            number=hit.rank,
            document_id=hit.document_id,
            filename=hit.filename,
            chunk_index=hit.chunk_index,
            text=hit.text,
            score=hit.score,
        )
        for hit in search_result.results
    ]


#  * 질문 다시 쓰기 (이 파일 안에서만 사용)
#  - 이전 대화가 없거나(첫 질문), 설정(CHAT_QUERY_REWRITE)으로 꺼 두었으면 원래 질문 그대로 사용
#  - 다시 쓰기에 실패해도(LLM 장애) 답변 전체를 실패시키지 않고 원래 질문으로 검색
#    => 질문 다시 쓰기는 "검색을 더 잘하기 위한 보조 기능"이기 때문
async def _rewrite_question(question: str, history: list[dict[str, str]]) -> str:
    if not history or not settings.chat_query_rewrite:
        return question
    try:
        rewritten = await llm.chat_completion(build_rewrite_messages(question, history))
    except llm.LLMError as err:
        logger.warning(f"🟡 질문 다시 쓰기 실패 => 원래 질문으로 검색: {err!r}")
        return question
    return clean_rewritten_question(rewritten, fallback=question)


#  * 답변 준비 (이 파일 안에서만 사용) - 한 번에 받기 / 스트리밍 공통
#  - 대화방 확인 -> 이전 대화 불러오기 -> 질문 다시 쓰기 -> 근거 문서 찾기
async def _prepare(session: AsyncSession, user: User, dto: ChatReq) -> _ChatContext:
    # 1. 이어서 질문하는 경우: 대화방 확인 + 최근 대화 불러오기
    conversation = None
    history: list[dict[str, str]] = []
    if dto.conversation_id is not None:
        # 1-1. 내 대화방이 아니면 404
        conversation = await _get_conversation_or_404(session, user, dto.conversation_id)
        # 1-2. 최근 메시지 N개 => LLM에게 보낼 형식으로 변환
        messages = await chat_repository.get_recent_messages(
            session, conversation.id, settings.chat_history_messages
        )
        history = build_history([(message.role.value, message.content) for message in messages])

    # 2. 질문 다시 쓰기 (이전 대화가 있을 때만)
    search_query = await _rewrite_question(dto.question, history)

    # 3. 근거 문서 찾기
    sources = await _retrieve_sources(dto, search_query)

    # 4. DB 연결 반납
    #  - 아래에서 LLM이 답변을 만드는 동안(수 초 ~ 수십 초) DB를 쓰지 않으므로,
    #    commit으로 지금까지의 조회 작업(트랜잭션)을 끝내서 DB 연결을 연결 풀에 돌려줌
    #    => 여러 사람이 동시에 질문해도 DB 연결(최대 10개)이 모자라지 않음
    #  - 조회만 했으므로 commit해도 DB에 바뀌는 것은 없음
    await session.commit()

    return _ChatContext(
        conversation=conversation,
        history=history,
        search_query=search_query,
        sources=sources,
    )


#  * 질문 + 답변 저장 (이 파일 안에서만 사용) - 한 번에 받기 / 스트리밍 공통
#  - 대화방이 없으면(새 대화) 첫 질문의 앞부분을 제목으로 대화방을 새로 만듦
#  - 반환값: 저장한 대화방
async def _save_turn(
    session: AsyncSession,
    user: User,
    conversation: Conversation | None,
    question: str,
    context: _ChatContext,
    answer: str,
) -> Conversation:
    # 1. 새 대화면 대화방 만들기
    if conversation is None:
        # 제목이 너무 길면 앞부분만 (뒤에 "…" 표시)
        title = question if len(question) <= TITLE_LENGTH else question[:TITLE_LENGTH] + "…"
        conversation = await chat_repository.create_conversation(
            session, Conversation(user_id=user.id, title=title)
        )

    # 2. 질문 메시지 + 답변 메시지 저장
    await chat_repository.create_messages(
        session,
        [
            ChatMessage(
                conversation_id=conversation.id,
                role=ChatMessageRole.USER,
                content=question,
                search_query=context.search_query,
            ),
            ChatMessage(
                conversation_id=conversation.id,
                role=ChatMessageRole.ASSISTANT,
                content=answer,
                # ChatSourceRes 목록 => JSON으로 저장할 수 있는 딕셔너리 목록
                sources=[source.model_dump() for source in context.sources],
                model=settings.llm_model,
            ),
        ],
    )

    # 3. 대화방의 "마지막 대화 시각" 갱신 (대화방 목록을 최근 대화 순으로 보여주기 위함)
    #  - 메시지만 추가하면 대화방 줄은 바뀌지 않아서 updated_at이 자동으로 갱신되지 않음
    conversation.updated_at = datetime.now(UTC)
    conversation = await chat_repository.update_conversation(session, conversation)

    # 4. 저장 확정
    await session.commit()
    return conversation


# 걸린 시간 계산 (단위: 밀리초)
def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


# 챗봇 답변 API (한 번에 받기) - POST /chat/
# 대화 이어가기 + 저장
#  - answer_question(session, user, dto) - 이전 대화를 참고해서 답하고, 질문 + 답변 저장
async def answer_question(session: AsyncSession, user: User, dto: ChatReq) -> ChatRes:
    started_at = time.perf_counter()
    # 1. 답변 준비 (대화방 확인, 이전 대화, 질문 다시 쓰기, 근거 문서 찾기)
    context = await _prepare(session, user, dto)

    # 2. 근거 문서가 없으면 LLM을 호출하지 않고 바로 안내 (LLM이 지어내는 것을 원천 차단)
    if not context.sources:
        answer = NO_SOURCE_ANSWER
    else:
        # 3. LLM에게 답변 요청 (이전 대화도 함께 보냄)
        messages = build_messages(
            dto.question, context.sources, context.history, context.search_query
        )
        try:
            answer = await llm.chat_completion(messages)
        except llm.LLMError as err:
            logger.error(f"🔴 LLM 답변 생성 실패: {err!r}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=LLM_ERROR_MESSAGE,
            ) from err
    answer = answer.strip()

    # 4. 질문 + 답변 저장
    conversation = await _save_turn(
        session, user, context.conversation, dto.question, context, answer
    )

    # 5. Service -> Router
    return ChatRes(
        question=dto.question,
        search_query=context.search_query,
        answer=answer,
        model=settings.llm_model,
        sources=context.sources,
        elapsed_ms=_elapsed_ms(started_at),
        conversation_id=conversation.id,
        conversation_title=conversation.title,
    )


# SSE(Server-Sent Events) 한 건 만들기
#  - 형식: "event: 이벤트이름\ndata: JSON\n\n" (빈 줄로 한 건이 끝남)
#  - ensure_ascii=False: 한글을 \uXXXX 로 바꾸지 않고 그대로 보냄
def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# 챗봇 답변 API (스트리밍) - POST /chat/stream
#  - 근거 문서 검색은 "스트리밍을 시작하기 전에" 먼저 끝냄
#    => 검색 단계 에러(503 등)는 일반 에러 응답(HTTP 상태 코드)으로 보낼 수 있음
#    => 스트리밍이 시작되면 상태 코드(200)를 바꿀 수 없어서, 그 이후 에러는 error 이벤트로 알림
#  - 반환값: 프론트엔드로 보낼 SSE 문자열을 하나씩 내보내는 흐름(AsyncIterator)
#  * 대화 이어가기 + 저장
#  - stream_answer(session, user, dto) - 대화방 확인(없는 대화방이면 404)도 스트리밍 전에 함
async def stream_answer(session: AsyncSession, user: User, dto: ChatReq) -> AsyncIterator[str]:
    started_at = time.perf_counter()
    # 1. 답변 준비 (에러는 여기서 바로 HTTPException으로 발생)
    context = await _prepare(session, user, dto)
    # 2. 실제 스트리밍은 아래 함수가 담당 (StreamingResponse가 하나씩 꺼내서 전송)
    return _generate_events(session, user, dto.question, context, started_at)


# 스트리밍 이벤트 만들기 (이 파일 안에서만 사용)
#  - 프론트엔드가 받는 이벤트 순서
#    1) sources: 근거 문서 목록 (답변보다 먼저 보내서 화면에 출처를 미리 보여줌)
#    2) token  : 답변 조각 (여러 번) - {"text": "연차는"}, {"text": " 3근무일"} ...
#    3) done   : 답변 끝 - {"model": "qwen3.5:9b", "elapsed_ms": 4210, ...}
#       (도중에 LLM 장애가 나면 done 대신 error: {"message": "..."})
#  * done 이벤트에 대화방 정보 + 답변이 끝나면 질문/답변 저장
#  - done: {"model", "elapsed_ms", "conversation_id", "conversation_title", "search_query"}
#    => 프론트엔드는 다음 질문 때 conversation_id를 보내서 대화를 이어감
#  - 사용자가 "중지"하면 연결이 끊기면서 이 함수가 중간에 멈춤 => 저장 코드까지 오지 않음
async def _generate_events(
    session: AsyncSession,
    user: User,
    question: str,
    context: _ChatContext,
    started_at: float,
) -> AsyncIterator[str]:
    # 1. 근거 문서 목록
    yield _sse("sources", [source.model_dump() for source in context.sources])

    # 2. 근거 문서가 없으면 LLM을 호출하지 않고 안내 문구만 보냄
    if not context.sources:
        answer = NO_SOURCE_ANSWER
        yield _sse("token", {"text": NO_SOURCE_ANSWER})
    else:
        # 3. LLM 답변을 조각조각 받아서 그대로 전달
        # 받은 조각을 이어 붙여 두었다가 답변이 끝나면 저장
        messages = build_messages(question, context.sources, context.history, context.search_query)
        pieces: list[str] = []
        try:
            async for piece in llm.stream_chat_completion(messages):
                pieces.append(piece)
                yield _sse("token", {"text": piece})
        except llm.LLMError as err:
            logger.error(f"🔴 LLM 스트리밍 답변 실패: {err!r}")
            yield _sse("error", {"message": LLM_ERROR_MESSAGE})
            return
        answer = "".join(pieces).strip()

    # 4. 질문 + 답변 저장
    #  - 저장에 실패해도 답변은 이미 화면에 보였으므로, error 이벤트로 "저장 실패"만 알림
    try:
        conversation = await _save_turn(
            session, user, context.conversation, question, context, answer
        )
    except SQLAlchemyError as err:
        logger.error(f"🔴 대화 저장 실패 (user_id={user.id}): {err!r}")
        await session.rollback()
        yield _sse("error", {"message": SAVE_ERROR_MESSAGE})
        return

    # 5. 답변 끝
    yield _sse(
        "done",
        {
            "model": settings.llm_model,
            "elapsed_ms": _elapsed_ms(started_at),
            "conversation_id": conversation.id,
            "conversation_title": conversation.title,
            "search_query": context.search_query,
        },
    )


# LLM 연결 상태 확인 API - GET /chat/status
async def get_status() -> ChatStatusRes:
    try:
        await llm.check_llm_connection()
    except llm.LLMError as err:
        return ChatStatusRes(model=settings.llm_model, available=False, message=str(err))
    return ChatStatusRes(model=settings.llm_model, available=True)


# ─────────────────────────────────────────────
#  * 대화 이력(대화방) API
#  - 내 대화방 목록 / 대화방 열기 / 제목 변경 / 삭제
#  - 모든 API는 "내 대화방"만 다룰 수 있음 (관리자도 다른 사람의 대화는 볼 수 없음)
# ─────────────────────────────────────────────


# 내 대화방 목록 조회(R-L) API - GET /chat/conversations
#  - document/service.py의 read_documents_list와 같은 방식
async def read_conversations_list(
    session: AsyncSession,
    user: User,
    query: ConversationReadListQuery,
) -> ConversationReadListRes:
    # 1. 페이지 번호 -> 건너뛸 개수(offset) 계산
    offset = (query.page - 1) * query.size
    # 2. Service -> Repository
    conversations, total = await chat_repository.get_conversations_list(
        session,
        user_id=user.id,
        offset=offset,
        limit=query.size,
    )
    # 3. 전체 페이지 수 계산
    total_pages = math.ceil(total / query.size)
    # 4. SQLAlchemy 객체 목록 -> Pydantic Response 모델 변환
    data = ConversationReadListRes(
        items=[ConversationRes.model_validate(conversation) for conversation in conversations],
        total=total,
        page=query.page,
        size=query.size,
        total_pages=total_pages,
    )
    # 5. Service -> Router
    return data


# 대화방 열기(R-D) API - GET /chat/conversations/{conversation_id}
#  - 대화방 정보 + 메시지 전체 (오래된 순)
async def read_conversation(
    session: AsyncSession,
    user: User,
    conversation_id: int,
) -> ConversationDetailRes:
    # 1. 대화방 조회 (내 대화방이 아니면 404)
    conversation = await _get_conversation_or_404(session, user, conversation_id)
    # 2. 메시지 전체 조회
    messages = await chat_repository.get_messages(session, conversation.id)
    # 3. SQLAlchemy 객체 -> Pydantic Response 모델 변환
    data = ConversationDetailRes(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[ChatMessageRes.model_validate(message) for message in messages],
    )
    # 4. Service -> Router
    return data


# 대화방 제목 변경(U) API - PATCH /chat/conversations/{conversation_id}
async def update_conversation(
    session: AsyncSession,
    user: User,
    conversation_id: int,
    dto: ConversationUpdateReq,
) -> ConversationRes:
    # 1. 대화방 조회 (내 대화방이 아니면 404)
    conversation = await _get_conversation_or_404(session, user, conversation_id)
    # 2. 제목 변경
    conversation.title = dto.title
    # 3. Service -> Repository
    conversation = await chat_repository.update_conversation(session, conversation)
    # 4. 변경 확정(commit)
    await session.commit()
    # 5. SQLAlchemy 객체 -> Pydantic Response 모델 변환 후 Service -> Router
    return ConversationRes.model_validate(conversation)


# 대화방 삭제(D) API - DELETE /chat/conversations/{conversation_id}
#  - 대화방 안의 메시지도 함께 삭제됨 (DB의 ondelete="CASCADE")
async def delete_conversation(
    session: AsyncSession,
    user: User,
    conversation_id: int,
) -> ConversationDeleteRes:
    # 1. 대화방 조회 (내 대화방이 아니면 404)
    conversation = await _get_conversation_or_404(session, user, conversation_id)
    # 2. Service -> Repository
    await chat_repository.delete_conversation(session, conversation)
    # 3. 삭제 확정(commit)
    await session.commit()
    # 4. Service -> Router
    return ConversationDeleteRes(success=True, id=conversation_id)


# 내 대화방 조회 + 없으면 404 (이 파일 안에서만 사용)
#  - 다른 사람의 대화방도 403(권한 없음)이 아니라 404(없음)로 응답
#    => "그 번호의 대화방이 존재한다"는 사실조차 알려주지 않기 위함
async def _get_conversation_or_404(
    session: AsyncSession,
    user: User,
    conversation_id: int,
) -> Conversation:
    conversation = await chat_repository.get_conversation_by_id(session, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="존재하지 않는 대화방입니다.",
        )
    return conversation
