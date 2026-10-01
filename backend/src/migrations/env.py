#  * 이 파일 전체를 "비동기(async) 엔진" 방식으로 다시 작성함
#  alembic init -t async 템플릿을 기반으로 작성
#
# 📌 사용법 (backend/ 폴더에서 실행)
#  - 마이그레이션 파일 자동 생성: uv run alembic revision --autogenerate -m "변경 내용 설명"
#  - DB에 마이그레이션 적용     : uv run alembic upgrade head
#  - 한 단계 되돌리기           : uv run alembic downgrade -1

import asyncio  # 비동기 함수를 실행하기 위한 파이썬 표준 라이브러리
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.base import TARGET_SCHEMA, Base
from src.core.config import get_settings

#  * 모델 파일 import
#  - 모델 파일을 import 해야 그 안의 테이블 정보가 Base.metadata에 등록됨
#  - ⚠️ 새 모델 파일(models.py)을 만들면 반드시 여기에 한 줄 추가해야 alembic이 인식함!
#  - import만 하고 코드에서 직접 사용하지는 않으므로 "noqa: F401"로 ruff 경고를 끔
from src.services.iam.auth import models as auth_models  # noqa: F401
from src.services.iam.user import models as user_models  # noqa: F401
from src.services.rag.chat import models as chat_models  # noqa: F401
from src.services.rag.document import models as document_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
# (alembic.ini 파일의 설정값에 접근할 수 있게 해주는 객체)
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# (alembic.ini의 [loggers] 설정대로 로그 출력 방식을 설정)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#  * target_metadata = None -> Base.metadata
#  - alembic은 target_metadata(우리 코드의 테이블 정보)와 실제 DB를 비교해서
#    "무엇이 달라졌는지"를 찾아 마이그레이션 파일을 자동으로 만들어 줌
target_metadata = Base.metadata

#  * DB 주소를 alembic.ini가 아니라 .env(config.py)에서 가져옴
#  - 비밀번호가 포함된 DB 주소를 alembic.ini(git에 올라가는 파일)에 적지 않기 위함
#  - config.set_main_option()으로 alembic.ini에 주소를 넣는 방법도 있지만,
#    비밀번호에 % 문자가 있으면 에러가 나기 때문에 주소를 직접 넘기는 방식을 사용
settings = get_settings()


#  * alembic이 비교할 "스키마"를 rag_practice 하나로 제한하는 필터 함수
#  - Supabase DB에는 public, auth, storage 등 Supabase가 사용하는 스키마가 이미 존재함
#  - 필터 없이 모든 스키마를 비교하면, alembic이 "우리 코드에 없는 테이블"로 판단하여
#    Supabase의 테이블을 삭제(drop)하는 마이그레이션을 만들 수 있음 => 매우 위험!
#  - type_ == "schema" 일 때 name이 rag_practice인 경우만 True(비교 대상)를 반환
#    (기본 스키마인 public은 name이 None으로 들어오므로 False => 제외됨)
def include_name(name, type_, parent_names) -> bool:
    if type_ == "schema":
        return name == TARGET_SCHEMA
    return True


#  * offline/online 모드에서 공통으로 사용하는 설정을 한 곳에 모음
#  - include_schemas=True: public 외의 스키마(rag_practice)도 비교 대상에 포함
#  - include_name: 위의 필터 함수로 rag_practice 스키마만 비교
#  - version_table_schema: alembic이 "현재 몇 번째 마이그레이션까지 적용했는지" 기록하는
#    alembic_version 테이블도 rag_practice 스키마에 만듦 (public 스키마를 건드리지 않음)
CONFIGURE_OPTIONS = {
    "target_metadata": target_metadata,
    "include_schemas": True,
    "include_name": include_name,
    "version_table_schema": TARGET_SCHEMA,
}


# Run migrations in 'offline' mode.
# (오프라인 모드: DB에 직접 연결하지 않고, 실행할 SQL문만 화면에 출력)
# 예) uv run alembic upgrade head --sql
def run_migrations_offline() -> None:
    context.configure(
        url=settings.async_db_url,  # alembic.ini 주소 -> .env의 DB 주소로
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONFIGURE_OPTIONS,
    )

    with context.begin_transaction():
        context.run_migrations()


#  * 실제 마이그레이션 실행 부분을 별도 함수로 분리
#  - alembic 내부는 동기(sync) 방식으로 동작하므로,
#    비동기 연결의 run_sync()를 통해 이 동기 함수를 실행함
def do_run_migrations(connection: Connection) -> None:
    #  * rag_practice 스키마가 없으면 먼저 생성
    #  - alembic_version 테이블을 rag_practice 스키마에 만들기 때문에 스키마가 먼저 있어야 함
    #  - IF NOT EXISTS: 이미 있으면 아무것도 하지 않음 (여러 번 실행해도 안전)
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TARGET_SCHEMA}"'))
    connection.commit()  # 스키마 생성을 먼저 확정

    context.configure(connection=connection, **CONFIGURE_OPTIONS)

    with context.begin_transaction():
        context.run_migrations()


# 비동기 엔진으로 DB에 연결하여 마이그레이션 실행
async def run_async_migrations() -> None:
    # 마이그레이션 전용 엔진 생성
    #  - poolclass=pool.NullPool: 커넥션을 보관(풀)하지 않고 한 번 쓰고 바로 닫음
    #    (마이그레이션은 잠깐 실행되고 끝나므로 커넥션 풀이 필요 없음)
    #  - prepare_threshold=None: Supabase Transaction pooler 대응 (src/core/database.py 참고)
    connectable = create_async_engine(
        settings.async_db_url,
        poolclass=pool.NullPool,
        connect_args={"prepare_threshold": None},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()  # 엔진 종료 - 남은 커넥션 정리


# Run migrations in 'online' mode.
# (온라인 모드: 실제 DB에 연결해서 마이그레이션을 실행)
def run_migrations_online() -> None:
    # asyncio.run(): 일반 함수 안에서 비동기 함수(run_async_migrations)를 실행
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
