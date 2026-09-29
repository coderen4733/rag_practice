from collections.abc import AsyncGenerator

from sqlalchemy import text  # 순수 SQL(SELECT 1) 실행용
from sqlalchemy.ext.asyncio import (  # for 비동기 DB 연결
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings

# get_settings()를 호출하여 환경변수 객체 가져오기
settings = get_settings()


# 비동기 엔진 생성
async_engine = create_async_engine(
    settings.async_db_url,  # DB 연결 주소
    #  * echo=True -> settings.db_echo
    #  - 실행되는 SQL을 콘솔에 출력하면 디버깅에 유용하지만, 운영 환경에서는 로그가 너무 많아짐
    #  - .env의 DB_ECHO 값으로 켜고 끌 수 있게 변경 (기본값 False)
    echo=settings.db_echo,
    future=True,  # SQLAlchemy 2.0 버전의 새로운 스타일을 구버전에도 강제 적용(생략해도 무방)
    # 1. 연결 풀 크기(중요)
    # Supabase Postgres DB 무료티어는 최대 커넥션 수가 약 60개로 제한됨
    # 아래 설정은 5+5=10개의 커넥션으로 설정 => 서버를 3대로 늘리면 30개 커넥션 사용(안전)
    pool_size=5,  # 유지할 기본 커넥션 수 (기본값: 5)
    max_overflow=5,  # 추가 생성 최대 커넥션 수 (기본값: 10)
    pool_timeout=15,  # 사용 가능 연결이 없을 때 대기하는 최대 시간(초) (기본값: 30)
    # 2. 연결 상태 관리 - 비활성화(Sleep) 대응
    pool_recycle=1800,  # 1800초(30분)마다 연결을 자동 갱신 (Supabase와의 유령 커넥션 방지)
    pool_pre_ping=True,  # DB가 깨어있는지, 연결이 살아있는지 쿼리 전 항상 체크
    # 3. 드라이버 전달 옵션
    connect_args={
        # 연결 타임아웃(DB 서버에 처음 연결할 때 타임아웃 시간)
        "connect_timeout": 10,
        # 쿼리 실행 타임아웃(단일 SQL문 실행 시 허용 최대 시간. 서버 마비 방지)
        # ※ 주의: Supabase "Transaction pooler"(포트 6543) 주소를 쓰면 이 옵션이 무시될 수 있음
        #   (Direct 연결(5432) 또는 Session pooler 주소에서는 정상 동작)
        "options": "-c statement_timeout=8000",
        #  * prepared statement(미리 준비된 쿼리) 자동 사용 끄기
        #  - psycopg3는 같은 쿼리를 5번 이상 실행하면 자동으로 "prepared statement"로 만들어 재사용
        #  - 그런데 Supabase "Transaction pooler"(포트 6543)는 요청마다 실제 DB 연결이 바뀌어서
        #    "prepared statement ... does not exist" 같은 에러가 랜덤하게 발생할 수 있음
        #  - None으로 설정하면 이 기능을 끔 => 어떤 Supabase 연결 방식에서도 안전하게 동작
        "prepare_threshold": None,
    },
)


# 세션 생성 - 요청마다 새로운 세션(트랜잭션 단위)을 찍어냄 (트랜잭션 동작 제어하는 인자를 받음)
async_session_factory = async_sessionmaker(
    bind=async_engine,  # 세션이 DB와 통신할 때 사용할 비동기 엔진 객체 지정 (필수)
    class_=AsyncSession,  # 생성할 세션의 클래스 타입 지정. 비동기이므로 비동기세션으로 지정 (필수)
    expire_on_commit=False,  # 트랜잭션 커밋 시 세션의 객체들의 데이터를 만료시킬지? (False 추천)
    autoflush=True,  # 쿼리를 실행하기 직전에 쌓인 변경 사항(추가/수정/삭제)을 자동으로 DB에 반영?
    info={"purpose": "web_api"},  # 세션 객체에 메타데이터 저장을 원할 때 사용요 (선택 사항)
)


# DB 연결 확인용 함수 - src/main.py의 lifespan에서 사용
async def check_db_connection() -> None:
    try:
        async with async_engine.connect() as conn:  # 비동기 컨텍스트 매니저(async with)
            # await conn.execute(text("SELECT 1"))
            result = await conn.scalar(text("SELECT 1"))  # .scalar()로 결과값 받기
            if result == 1:
                # logger.info("🟢 DB 연결에 성공했습니다.")
                return
            else:
                # 연결은 되었으나 응답이 이상한 상태(DB 자체에 프로그램 오류가 있는 경우) - 위험!
                err_message = f"DB의 상태가 비정상적입니다. scalar value: {result}"
                # logger.critical(f"🔴 {err_message}")
                raise Exception(err_message)
    except Exception as err:
        # DB 드라이버가 던진 구체적 실패 원인(비번 틀림, 타임아웃 등)을 로깅
        # logger.error(f"🔴 DB 연결에 실패했습니다. {err}")
        raise err


# DB 연결 종료 함수 - src/main.py의 lifespan에서 사용
async def close_db() -> None:
    try:
        await async_engine.dispose()  # 비동기 엔진 종료(dispose) - 풀에 남은 커넥션 닫기
        # logger.info("🟢 DB 엔진이 안전하게 종료되었습니다.")
    except Exception as err:
        # logger.critical(f"🔴 DB 엔진 종료 중 에러가 발생했습니다. {err}")
        raise err


# Router Depends로 사용할 의존성 함수
# 요청이 들어올 때마다 세션을 하나 만들어 주고,
# 요청 처리가 끝나면(with 블록 종료) 자동으로 세션 닫음
async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session  # 성공 시 명시적 커밋 or 라우터 내부에서 처리
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
