"""create conversations and chat_messages tables

Revision ID: d5e2a8c41f70
Revises: b7c3e91d2a45
Create Date: 2026-10-01 10:00:00.000000

"""

#  * 대화방(conversations), 대화 메시지(chat_messages) 테이블 생성
#  - 변경: 대화 이어가기 + 대화 이력을 위한 2개의 테이블 생성
#  - src/services/rag/chat/models.py 의 Conversation, ChatMessage 모델과 똑같은 구조
#  - 적용 명령어: uv run alembic upgrade head
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# revision: 이 파일의 고유 번호 / down_revision: 바로 이전 마이그레이션 파일의 번호
revision: str = "d5e2a8c41f70"
down_revision: str | Sequence[str] | None = "b7c3e91d2a45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. conversations 테이블 생성 (대화방)
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 사용자가 삭제되면 그 사용자의 대화방도 함께 삭제
        sa.ForeignKeyConstraint(["user_id"], ["rag_practice.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="rag_practice",
    )
    # 1-1. user_id 색인 생성 ("내 대화방 목록" 조회용)
    op.create_index(
        op.f("ix_rag_practice_conversations_user_id"),
        "conversations",
        ["user_id"],
        unique=False,
        schema="rag_practice",
    )

    # 2. chat_messages 테이블 생성 (대화 메시지)
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "user",
                "assistant",
                name="chatmessagerole",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_query", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 대화방이 삭제되면 그 안의 메시지도 함께 삭제
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["rag_practice.conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="rag_practice",
    )
    # 2-1. conversation_id 색인 생성 ("대화방의 메시지 목록" 조회용)
    op.create_index(
        op.f("ix_rag_practice_chat_messages_conversation_id"),
        "chat_messages",
        ["conversation_id"],
        unique=False,
        schema="rag_practice",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 되돌리기: upgrade와 반대 순서로 삭제 (메시지 -> 대화방)
    #  - chat_messages가 conversations를 참조(외래키)하므로 chat_messages를 먼저 삭제해야 함
    op.drop_index(
        op.f("ix_rag_practice_chat_messages_conversation_id"),
        table_name="chat_messages",
        schema="rag_practice",
    )
    op.drop_table("chat_messages", schema="rag_practice")
    op.drop_index(
        op.f("ix_rag_practice_conversations_user_id"),
        table_name="conversations",
        schema="rag_practice",
    )
    op.drop_table("conversations", schema="rag_practice")
