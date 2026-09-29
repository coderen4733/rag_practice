"""rename token_hash to hashed_token

Revision ID: 865ad4f171ea
Revises: 4ea8f8cdce81
Create Date: 2026-09-29 16:14:51.241212

"""

# [수정] refresh_tokens 테이블의 컬럼 이름 변경 마이그레이션 (token_hash -> hashed_token)
#  - 기존: 없음 (새로 추가한 마이그레이션 파일)
#  - 변경: DB의 컬럼 이름을 models.py(RefreshToken.hashed_token)와 똑같이 맞춤
#
#  - ⚠️ 이 파일은 --autogenerate 로 만들지 않고 직접 작성함
#    => autogenerate는 "이름 변경"을 알아채지 못하고,
#       "token_hash 컬럼 삭제 + hashed_token 컬럼 새로 추가"로 만들어 버림
#    => 그러면 컬럼 안의 데이터(저장된 리프레시 토큰)가 모두 사라지고,
#       기본키(PK) 컬럼을 삭제하려다 에러가 날 수도 있음
#    => op.alter_column(new_column_name=...) 을 쓰면 데이터는 그대로 두고 "이름만" 바꿈
#
#  - 기존 마이그레이션(4ea8f8cdce81_init.py)은 절대 수정하지 않음
#    => 이미 DB에 적용된 파일을 고치면, DB 상태와 마이그레이션 기록이 서로 어긋나게 됨
#    => 대신 "변경 사항"을 새 파일로 추가하는 것이 alembic의 기본 사용법
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
# revision: 이 파일의 고유 번호 / down_revision: 바로 이전 마이그레이션 파일의 번호(init)
# => alembic은 down_revision을 따라가며 init -> 이 파일 순서로 실행함
revision: str = "865ad4f171ea"
down_revision: str | Sequence[str] | None = "4ea8f8cdce81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 컬럼 이름 변경: token_hash -> hashed_token
    # 실행되는 SQL: ALTER TABLE rag_practice.refresh_tokens
    #              RENAME COLUMN token_hash TO hashed_token;
    #  - 기본키(PK) 설정과 저장된 데이터는 그대로 유지되고 "이름만" 바뀜
    op.alter_column(
        "refresh_tokens",
        "token_hash",
        new_column_name="hashed_token",
        schema="rag_practice",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 되돌리기(downgrade): upgrade와 반대로 hashed_token -> token_hash
    op.alter_column(
        "refresh_tokens",
        "hashed_token",
        new_column_name="token_hash",
        schema="rag_practice",
    )
