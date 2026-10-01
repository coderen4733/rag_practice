#  * 대화방(Conversation), 대화 메시지(ChatMessage) 테이블 DB 작업
#  - 대화방 생성/조회/수정/삭제/목록 조회, 메시지 저장/조회
#  - document/repository.py와 같은 방식: commit은 하지 않고 service에서 함

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.rag.chat.models import ChatMessage, Conversation


# 대화방(Conversation) 생성(C)
async def create_conversation(
    session: AsyncSession,
    conversation: Conversation,
) -> Conversation:
    # 1. Repository -> DB
    session.add(conversation)
    await session.flush()  # INSERT를 DB에 보내서 id를 발급받음 (확정은 service에서)
    # 2. conversation 객체 갱신 (DB가 채운 기본값을 다시 읽어옴)
    await session.refresh(conversation)
    # 3. Repository -> Service
    return conversation


# 대화방(Conversation) 조회(R-D) by id
async def get_conversation_by_id(
    session: AsyncSession,
    conversation_id: int,
) -> Conversation | None:
    # 1. Repository <- DB (id는 PK이므로 session.get()으로 조회, 없으면 None)
    data = await session.get(Conversation, conversation_id)
    # 2. Repository -> Service
    return data


# 대화방(Conversation) 수정(U)
#  - service에서 값(title, updated_at)을 바꾼 conversation 객체를 DB에 반영
async def update_conversation(
    session: AsyncSession,
    conversation: Conversation,
) -> Conversation:
    # 1. Repository -> DB
    await session.flush()
    # 2. conversation 객체 갱신 (updated_at은 DB가 정하므로 다시 읽어옴)
    await session.refresh(conversation)
    # 3. Repository -> Service
    return conversation


# 대화방(Conversation) 삭제(D)
#  - 대화방 안의 메시지는 DB의 ondelete="CASCADE" 설정으로 함께 삭제됨
async def delete_conversation(
    session: AsyncSession,
    conversation: Conversation,
) -> None:
    # 1. Repository -> DB (확정은 service에서 commit)
    await session.delete(conversation)


# 내 대화방(Conversation) 목록 조회(R-L)
#  - 최근에 대화한 순서(updated_at 내림차순) + 페이지네이션
#  - 반환값: (현재 페이지의 대화방 목록, 내 전체 대화방 수)
async def get_conversations_list(
    session: AsyncSession,
    *,
    user_id: int,
    offset: int,
    limit: int,
) -> tuple[list[Conversation], int]:
    # 1. 필터 조건: 내 대화방만
    condition = Conversation.user_id == user_id

    # 2. Repository <- DB : 전체 개수 조회
    count_query = select(func.count()).select_from(Conversation).where(condition)
    total = await session.scalar(count_query) or 0

    # 3. Repository <- DB : 현재 페이지의 대화방 목록 조회 (최근 순 + id로 순서 고정)
    query = (
        select(Conversation)
        .where(condition)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    conversations = list(result.scalars().all())

    # 4. Repository -> Service
    return conversations, total


# 대화 메시지(ChatMessage) 여러 개 생성(C)
#  - 질문 메시지와 답변 메시지를 한 번에 저장할 때 사용
async def create_messages(
    session: AsyncSession,
    messages: list[ChatMessage],
) -> list[ChatMessage]:
    # 1. Repository -> DB
    #  - add_all: 여러 객체를 한 번에 추가 (추가한 순서대로 id가 발급됨 => 질문이 답변보다 앞)
    session.add_all(messages)
    await session.flush()
    # 2. Repository -> Service
    return messages


# 대화방의 메시지 전체 조회 (오래된 순)
#  - 대화방을 다시 열었을 때 화면에 보여줄 때 사용
async def get_messages(
    session: AsyncSession,
    conversation_id: int,
) -> list[ChatMessage]:
    # 1. Repository <- DB
    #  - id 순서 = 저장된 순서 (같은 시각에 저장된 질문/답변도 순서가 바뀌지 않음)
    query = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.asc())
    )
    result = await session.execute(query)
    # 2. Repository -> Service
    return list(result.scalars().all())


# 대화방의 최근 메시지 조회 (오래된 순으로 정렬해서 돌려줌)
#  - 이어서 질문할 때 LLM에게 "이전 대화"로 함께 보낼 메시지를 가져올 때 사용
#  - 예) limit=4 => 최근 질문 2개 + 답변 2개
async def get_recent_messages(
    session: AsyncSession,
    conversation_id: int,
    limit: int,
) -> list[ChatMessage]:
    # 0. 가져올 개수가 0이면 DB에 묻지 않고 바로 빈 목록
    if limit <= 0:
        return []
    # 1. Repository <- DB : 최신 메시지부터 limit개
    query = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    messages = list(result.scalars().all())
    # 2. 대화 순서(오래된 순)로 뒤집어서 Repository -> Service
    messages.reverse()
    return messages
