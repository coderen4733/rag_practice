#  * 대화방(Conversation), 대화 메시지(ChatMessage) 테이블 정의
#  - 대화 이어가기 + 대화 이력을 위해 2개의 테이블
#    - conversations : 대화방 1개 = 한 줄 (누구의 대화인지, 제목)
#    - chat_messages : 대화방 안의 질문/답변 1개 = 한 줄 (내용, 근거 문서, 모델 이름 등)
#
# 📌 "세션(session)"이 아니라 "대화방(conversation)"이라고 부르는 이유
#  - 이 프로젝트에서 session은 이미 "DB 세션(AsyncSession)"을 뜻하는 이름으로 쓰고 있음
#    => chat_session이라고 하면 코드에서 두 가지가 헷갈리기 쉬워서 conversation으로 이름 붙임
#
# 📌 relationship(테이블끼리 자동 연결)을 쓰지 않은 이유
#  - 비동기(async) 환경에서 relationship을 잘못 쓰면 "자동 조회(lazy load)" 에러가 나기 쉬움
#  - 그래서 외래키(conversation_id) 값만 두고, 필요한 메시지는 repository에서 직접 조회함

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base import Base
from src.services.rag.chat.enums import ChatMessageRole


# 대화방 (conversations 테이블)
class Conversation(Base):
    __tablename__ = "conversations"

    # 1. 기본 정보
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    # 대화방 제목 (처음 질문의 앞부분으로 자동 생성, 나중에 사용자가 바꿀 수 있음)
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 2. 대화방 주인
    #  - ondelete="CASCADE": 사용자가 삭제되면 그 사용자의 대화방도 함께 삭제
    #    (문서의 uploaded_by는 SET NULL이지만, 대화는 개인 기록이라 주인이 없으면 남길 이유가 없음)
    #  - index=True: "내 대화방 목록" 조회를 빠르게 하기 위한 색인
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # 3. 메타 정보 (documents 테이블과 같은 방식)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    # 마지막으로 바뀐 시각 (새 질문/답변이 추가되거나 제목을 바꾸면 갱신)
    #  => 대화방 목록을 "최근에 대화한 순서"로 보여줄 때 사용
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# 대화 메시지 (chat_messages 테이블)
#  - 질문 1개와 답변 1개가 각각 한 줄씩 저장됨
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    # 1. 기본 정보
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    # 1-1. 어느 대화방의 메시지인지
    #  - ondelete="CASCADE": 대화방을 삭제하면 그 안의 메시지도 DB가 함께 삭제
    #  - index=True: "대화방의 메시지 목록" 조회를 빠르게 하기 위한 색인
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # 1-2. 보낸 쪽 (user: 질문 / assistant: 답변)
    #  - 문서의 status와 같은 방식: DB에는 Enum의 "값"("user")을 문자열로 저장
    role: Mapped[ChatMessageRole] = mapped_column(
        SAEnum(
            ChatMessageRole,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # 1-3. 내용 (질문 또는 답변)
    #  - Text: 길이 제한이 없는 문자열 (답변은 길어질 수 있으므로 String(길이) 대신 사용)
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 2. 질문(user) 메시지에만 저장하는 값
    # 2-1. 실제 검색에 사용한 질문
    #  - 이어서 묻는 질문("그럼 신입사원은?")을 LLM이 "신입사원의 연차는 며칠인가?"처럼
    #    혼자서도 뜻이 통하는 질문으로 다시 쓴 결과 (다시 쓰지 않았으면 질문과 같음)
    #  - 검색 결과가 이상할 때 "무엇으로 검색했는지" 확인하는 용도
    search_query: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 3. 답변(assistant) 메시지에만 저장하는 값
    # 3-1. 답변의 근거로 사용한 문서 목록 (ChatSourceRes 목록을 JSON으로 저장)
    #  - JSON: 목록/딕셔너리를 그대로 저장할 수 있는 형식
    #    => 나중에 대화를 다시 열었을 때 답변 위에 근거 문서 카드를 그대로 다시 보여줌
    #  - 문서가 나중에 삭제되어도 "그때 어떤 내용을 근거로 답했는지"는 남음
    sources: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    # 3-2. 답변을 만든 LLM 모델 이름 (나중에 모델을 바꿔도 어떤 모델의 답인지 알 수 있음)
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # 4. 메타 정보
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
