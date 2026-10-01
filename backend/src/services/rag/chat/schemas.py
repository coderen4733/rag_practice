from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.services.rag.chat.enums import ChatMessageRole


# 챗봇 질문 - 요청(Req)
class ChatReq(BaseModel):
    # 질문 (앞뒤 공백 제거 후 1~1000자)
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
        Field(description="질문 (1~1000자)"),
    ]
    # 답변의 근거로 사용할 청크 수 (비워두면 서버 설정값 CHAT_TOP_K 사용, 기본 5)
    top_k: int | None = Field(default=None, ge=1, le=20, description="근거로 사용할 청크 수")
    # 특정 문서만 근거로 사용할 때 문서 id 목록 (비워두면 전체 문서)
    document_ids: list[int] | None = Field(default=None, max_length=50)
    # 이어서 질문할 대화방 id
    #  - 비워두면 새 대화방을 만들고, 값을 보내면 그 대화방의 이전 대화를 참고해서 답함
    conversation_id: int | None = Field(default=None, ge=1, description="이어서 질문할 대화방 id")


# 답변의 근거(출처) 1개 - 응답(Res)
#  - number: 답변 안의 [1], [2] 표시와 연결되는 번호
class ChatSourceRes(BaseModel):
    number: int
    document_id: int
    filename: str
    chunk_index: int
    text: str
    score: float


# 챗봇 답변 - 응답(Res) (POST /chat/)
class ChatRes(BaseModel):
    question: str  # 질문 (앞뒤 공백 제거된 값)
    # 검색에 실제로 사용한 질문
    #  - 이어서 묻는 질문은 LLM이 혼자서도 뜻이 통하는 질문으로 다시 씀 (아니면 question과 같음)
    search_query: str
    answer: str  # LLM이 만든 답변
    model: str  # 답변을 만든 LLM 모델 이름
    sources: list[ChatSourceRes]  # 답변의 근거로 사용한 청크 목록
    elapsed_ms: int  # 걸린 시간 (단위: 밀리초)
    # 이 질문/답변이 저장된 대화방 정보 (다음 질문 때 conversation_id로 보내면 이어짐)
    conversation_id: int
    conversation_title: str


# LLM 연결 상태 - 응답(Res) (GET /chat/status)
class ChatStatusRes(BaseModel):
    model: str  # 설정된 LLM 모델 이름
    available: bool  # 사용 가능 여부
    message: str | None = None  # 사용할 수 없을 때 이유


# ─────────────────────────────────────────────
#  * 대화 이력(대화방) API 요청/응답 형식
#  - 내 대화방 목록 / 대화방 열기(메시지 목록) / 제목 변경 / 삭제 API에서 사용
# ─────────────────────────────────────────────


# 대화방(Conversation) 조회 - 응답(Res)
#  - 대화방 목록, 제목 변경에서 공통으로 사용
class ConversationRes(BaseModel):
    # from_attributes=True: SQLAlchemy 객체를 Pydantic이 자동으로 변환할 수 있도록 설정
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime  # 마지막으로 대화한 시각 (목록 정렬 기준)


# 대화 메시지(ChatMessage) 1개 - 응답(Res)
class ChatMessageRes(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: ChatMessageRole  # user(질문) / assistant(답변)
    content: str  # 질문 또는 답변 내용
    search_query: str | None  # 검색에 사용한 질문 (질문 메시지만)
    # 근거 문서 목록 (답변 메시지만) - DB의 JSON을 ChatSourceRes 목록으로 다시 바꿔서 보냄
    sources: list[ChatSourceRes] | None
    model: str | None  # 답변을 만든 LLM 모델 이름 (답변 메시지만)
    created_at: datetime


# 대화방(Conversation) 열기(R-D) - 응답(Res)
#  - 대화방 정보 + 메시지 전체 (오래된 순)
class ConversationDetailRes(ConversationRes):
    messages: list[ChatMessageRes]


# 내 대화방(Conversation) 목록 조회(R-L) - 요청(Query)
#  - 예) /chat/conversations?page=2&size=20
class ConversationReadListQuery(BaseModel):
    page: int = Field(default=1, ge=1, description="페이지 번호 (1부터 시작)")
    size: int = Field(default=20, ge=1, le=100, description="한 페이지당 대화방 수 (최대 100)")


# 내 대화방(Conversation) 목록 조회(R-L) - 응답(Res)
class ConversationReadListRes(BaseModel):
    items: list[ConversationRes]  # 현재 페이지의 대화방 목록 (최근 대화 순)
    total: int  # 내 전체 대화방 수
    page: int  # 현재 페이지 번호
    size: int  # 한 페이지당 대화방 수
    total_pages: int  # 전체 페이지 수


# 대화방(Conversation) 제목 변경(U) - 요청(Req)
class ConversationUpdateReq(BaseModel):
    # 새 제목 (앞뒤 공백 제거 후 1~100자)
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
        Field(description="대화방 제목 (1~100자)"),
    ]


# 대화방(Conversation) 삭제(D) - 응답(Res)
class ConversationDeleteRes(BaseModel):
    success: bool = True
    id: int  # 삭제된 대화방 id
