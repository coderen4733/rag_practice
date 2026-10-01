from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

# StreamingResponse: 응답을 한 번에 보내지 않고, 만들어지는 대로 조금씩 보내는 응답
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.response import ResponseSchema
from src.core.database import get_db_session
from src.services.iam.auth.dependencies import CurrentUser
from src.services.rag.chat import service as chat_service
from src.services.rag.chat.schemas import (
    ChatReq,
    ChatRes,
    ChatStatusRes,
    ConversationDeleteRes,
    ConversationDetailRes,
    ConversationReadListQuery,
    ConversationReadListRes,
    ConversationRes,
    ConversationUpdateReq,
)

chat_router = APIRouter()


# 챗봇 답변 API (한 번에 받기) - 로그인한 사용자 누구나
@chat_router.post(
    "/",
    response_model=ResponseSchema[ChatRes],
    status_code=status.HTTP_200_OK,
)
async def answer_question(
    dto: ChatReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await chat_service.answer_question(session, current_user, dto)
    # 2. Router -> FrontEnd
    return {
        "message": "답변 생성에 성공했습니다.",
        "data": data,
    }


# 챗봇 답변 API (스트리밍) - 로그인한 사용자 누구나
#  - 응답 형식: text/event-stream (SSE)
#      event: sources / data: [...]        <- 근거 문서 목록
#      event: token   / data: {"text": ..} <- 답변 조각 (여러 번)
#      event: done    / data: {...}        <- 끝 (도중 장애 시 event: error)
#  - DB 세션은 스트리밍이 "끝난 뒤"에 닫힘 => 답변이 끝난 뒤 질문/답변을 저장할 수 있음
#    (FastAPI 0.118 이후: yield를 쓰는 의존성(get_db_session)의 뒷정리는 응답을 다 보낸 뒤 실행)
@chat_router.post("/stream")
async def stream_answer(
    dto: ChatReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> StreamingResponse:
    # 1. Router <- Service (근거 문서 검색까지 끝난 뒤, 이벤트를 내보내는 흐름을 받음)
    events = await chat_service.stream_answer(session, current_user, dto)
    # 2. Router -> FrontEnd (이벤트를 하나씩 전송)
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            # 중간에서 응답을 저장(캐시)하지 않도록 함
            "Cache-Control": "no-cache",
            # Nginx가 응답을 모았다가 한 번에 보내지 않도록 함 (나중에 Docker 납품 시 필요)
            "X-Accel-Buffering": "no",
        },
    )


# LLM 연결 상태 API - 로그인한 사용자 누구나 (시스템 상태 화면에서 사용)
@chat_router.get(
    "/status",
    response_model=ResponseSchema[ChatStatusRes],
    status_code=status.HTTP_200_OK,
)
async def get_status(current_user: CurrentUser) -> dict:
    # 1. Router <- Service
    data = await chat_service.get_status()
    # 2. Router -> FrontEnd
    return {
        "message": "LLM 상태 조회에 성공했습니다.",
        "data": data,
    }


# ─────────────────────────────────────────────
#  * 대화 이력(대화방) API
#  - 로그인한 사용자 누구나 "내 대화방"만 조회/수정/삭제 가능
#    (다른 사람의 대화방 id를 넣으면 404)
# ─────────────────────────────────────────────


# 내 대화방 목록 조회(R-L) API - 최근 대화 순
@chat_router.get(
    "/conversations",
    response_model=ResponseSchema[ConversationReadListRes],
    status_code=status.HTTP_200_OK,
)
async def read_conversations_list(
    # 페이지 쿼리 파라미터 (예: ?page=1&size=20)
    query: Annotated[ConversationReadListQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await chat_service.read_conversations_list(session, current_user, query)
    # 2. Router -> FrontEnd
    return {
        "message": "대화방 목록 조회에 성공했습니다.",
        "data": data,
    }


# 대화방 열기(R-D) API - 대화방 정보 + 메시지 전체
@chat_router.get(
    "/conversations/{conversation_id}",
    response_model=ResponseSchema[ConversationDetailRes],
    status_code=status.HTTP_200_OK,
)
async def read_conversation(
    conversation_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await chat_service.read_conversation(session, current_user, conversation_id)
    # 2. Router -> FrontEnd
    return {
        "message": "대화방 조회에 성공했습니다.",
        "data": data,
    }


# 대화방 제목 변경(U) API
@chat_router.patch(
    "/conversations/{conversation_id}",
    response_model=ResponseSchema[ConversationRes],
    status_code=status.HTTP_200_OK,
)
async def update_conversation(
    conversation_id: int,
    dto: ConversationUpdateReq,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await chat_service.update_conversation(session, current_user, conversation_id, dto)
    # 2. Router -> FrontEnd
    return {
        "message": "대화방 제목 변경에 성공했습니다.",
        "data": data,
    }


# 대화방 삭제(D) API - 대화방 안의 메시지도 함께 삭제
@chat_router.delete(
    "/conversations/{conversation_id}",
    response_model=ResponseSchema[ConversationDeleteRes],
    status_code=status.HTTP_200_OK,
)
async def delete_conversation(
    conversation_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await chat_service.delete_conversation(session, current_user, conversation_id)
    # 2. Router -> FrontEnd
    return {
        "message": "대화방 삭제에 성공했습니다.",
        "data": data,
    }
