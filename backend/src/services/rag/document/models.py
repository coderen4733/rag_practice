#  * 문서(Document) 테이블 정의
#  - 업로드된 문서의 "정보"를 저장하는 documents 테이블
#    => 문서의 실제 내용(청크 원문 + 벡터)은 Postgres가 아니라 Qdrant에 저장됨
#    => 이 테이블은 "어떤 문서가 등록되어 있는지" 목록/상태를 관리하는 용도

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base import Base
from src.services.rag.document.enums import DocumentStatus


class Document(Base):
    __tablename__ = "documents"

    # 1. 기본 정보
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    filename: Mapped[str] = mapped_column(
        String(255),  # 업로드한 파일 이름 (예: 휴가규정.md)
        nullable=False,
    )
    file_extension: Mapped[str] = mapped_column(
        String(10),  # 확장자 (예: .md) - 나중에 PDF 등 형식별로 구분할 때 사용
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,  # 파일 크기 (단위: 바이트)
        nullable=False,
    )

    # 2. 처리 정보
    # 2-1. 처리 상태 (processing / completed / failed)
    #  - user의 role과 같은 방식: DB에는 Enum의 "값"("completed")을 문자열로 저장
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(
            DocumentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=DocumentStatus.PROCESSING,
        server_default=DocumentStatus.PROCESSING.value,
        nullable=False,
    )
    # 2-2. Qdrant에 저장된 청크 개수 (처리 완료 전에는 0)
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    # 2-3. 처리 실패 시 사용자에게 보여줄 실패 이유 (성공하면 None)
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # 3. 업로드한 사용자
    #  - ondelete="SET NULL": 업로드한 사용자가 삭제되어도 문서는 남기고, 이 값만 비움(NULL)
    #    (refresh_tokens의 CASCADE는 "같이 삭제", SET NULL은 "연결만 끊기")
    #  - index=True: "특정 사용자가 올린 문서" 검색을 빠르게 하기 위한 색인
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # 4. 메타 정보 (users 테이블과 같은 방식)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
