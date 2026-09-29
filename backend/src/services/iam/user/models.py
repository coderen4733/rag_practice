from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, false, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

#  * Base를 이 파일에서 직접 만들지 않고, 공통 Base(src/core/base.py)를 가져와서 사용
#  - 기존: class Base(AsyncAttrs, DeclarativeBase): pass 를 이 파일 안에서 정의
#  - 변경: 모든 모델이 같은 Base를 공유해야 alembic이 모든 테이블을 한 번에 인식할 수 있음
from src.core.base import Base
from src.services.iam.user.enums import UserRole


class User(Base):
    __tablename__ = "users"

    # 1. 기본 정보
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 2. 권한 정보
    # 2-1. RAG 권한('admin', 'manager', 'user')
    #  * values_callable 은 무엇인가?
    #  - 파이썬 Enum의 각 항목은 "이름(name)"과 "값(value)"을 가짐
    #      예) UserRole.USER => 이름: "USER", 값: "user"
    #  - SQLAlchemy의 Enum은 기본적으로 DB에 "이름"("USER")을 저장함
    #  - values_callable=lambda e: [m.value for m in e] 를 지정하면 "값"("user")을 저장함
    #      - lambda e: ... => e에는 UserRole 클래스가 들어옴
    #      - [m.value for m in e] => UserRole의 모든 항목의 값 목록 = ["admin", "manager", "user"]
    #  - 이 옵션이 꼭 필요한 이유:
    #    server_default와 이미 만들어진 마이그레이션은 "user"(값)를 기본값으로 사용하므로,
    #    옵션이 없으면 파이썬에서는 "USER", DB 기본값은 "user"로 서로 달라져서
    #    DB에서 읽어올 때 "user는 UserRole에 없는 이름"이라는 에러(LookupError)가 발생함
    #  - native_enum=False: Postgres 전용 ENUM 타입 대신 일반 VARCHAR(문자열)로 저장
    #    => 나중에 권한 종류를 추가할 때 DB 타입을 바꾸는 마이그레이션이 필요 없음
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            native_enum=False,
            length=50,
            # UserRole 클래스(e), 이름(m), 값(m.value)
            values_callable=lambda e: [m.value for m in e],  # 이름 대신 값으로 저장
        ),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )
    # 2-2. 계정 승인(True: 관리자 승인 완료 / False: 관리자 미승인 상태)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=false(),
        nullable=False,
    )

    # 3. 메타 정보
    #  - DateTime(timezone=True) => Postgres timestamptz
    #    입력 시각을 UTC로 변환해 저장하므로 서버 위치와 무관하게 같은 절대 시각을 가짐
    #    (타임존 자체는 저장되지 않음. 파이썬에서는 항상 UTC aware datetime을 사용할 것)
    #  - default/onupdate: 앱 시계 기준 (ORM 경유 시)
    #  - server_default: ORM 밖 INSERT 대비 안전망 (DB 시계 기준)
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
