"""create documents table

Revision ID: b7c3e91d2a45
Revises: 865ad4f171ea
Create Date: 2026-09-30 16:00:00.000000

"""

# [수정] documents 테이블 생성 마이그레이션 (새 파일)
#  - 기존: 없음
#  - 변경: 업로드된 문서의 정보(파일명, 처리 상태, 청크 수 등)를 저장하는 documents 테이블 생성
#  - src/services/rag/document/models.py 의 Document 모델과 똑같은 구조
#  - 적용 명령어: uv run alembic upgrade head
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# revision: 이 파일의 고유 번호 / down_revision: 바로 이전 마이그레이션 파일의 번호
revision: str = "b7c3e91d2a45"
down_revision: str | Sequence[str] | None = "865ad4f171ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. documents 테이블 생성
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_extension", sa.String(length=10), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "processing",
                "completed",
                "failed",
                name="documentstatus",
                native_enum=False,
                length=20,
            ),
            server_default="processing",
            nullable=False,
        ),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
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
        # 업로드한 사용자가 삭제되면 uploaded_by만 NULL로 비움 (문서는 유지)
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["rag_practice.users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="rag_practice",
    )
    # 2. uploaded_by 색인 생성 ("특정 사용자가 올린 문서" 검색용)
    op.create_index(
        op.f("ix_rag_practice_documents_uploaded_by"),
        "documents",
        ["uploaded_by"],
        unique=False,
        schema="rag_practice",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 되돌리기: upgrade와 반대 순서로 색인 삭제 -> 테이블 삭제
    op.drop_index(
        op.f("ix_rag_practice_documents_uploaded_by"),
        table_name="documents",
        schema="rag_practice",
    )
    op.drop_table("documents", schema="rag_practice")
