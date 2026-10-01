from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),  # user_id에 외래키 지정
        index=True,  # user_id로 검색 때 빠르게 찾도록 색인(index) 생성(모든 기기 로그아웃 기능 시)
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(
        String(45),  # IP 주소 최대 길이(IPv6 형식 최대 45자)에 맞춤
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),  # 평소엔 앱 서버 시계 기준
        server_default=func.now(),  # ORM 밖 INSERT 대비. DB 서버 시계 기준
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    hashed_token: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )  # 토큰 값 자체로 저장하면 해킹 시 위험하므로 해시하여 저장
