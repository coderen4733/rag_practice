"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
##  * 이 파일은 alembic revision 명령으로 "새 마이그레이션 파일을 만들 때 쓰는 틀(템플릿)"
##  - Union[A, B] -> A | B, typing.Sequence -> collections.abc.Sequence
##  - "##"로 시작하는 줄은 Mako(템플릿 엔진)의 주석이라, 생성되는 마이그레이션 파일에는 복사되지 않음
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}
