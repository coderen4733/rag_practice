import logging  # log 생성용 / 나중에 Grafana와 연동하기 쉬움
from contextlib import asynccontextmanager  # Lifespan 생성

from fastapi import FastAPI  # FastAPI로 Back-End 구성
from fastapi.middleware.cors import (
    CORSMiddleware,  # CORS 설정을 위한 Middleware
)

from src.api import api_router
from src.core.config import get_settings
from src.core.database import (
    check_db_connection,
    close_db,
)
from src.core.embedding import (
    check_embedding_connection,
    close_embedding,
    init_embedding,
)
from src.core.vector_db import (
    check_vector_db_connection,
    close_vector_db,
    ensure_collection,
    init_vector_db,
)

#  * 로깅 기본 설정
#  - level=logging.INFO: INFO 이상(INFO, WARNING, ERROR, CRITICAL)의 로그만 출력
#  - format: 로그 한 줄의 모양 => "시간 | 레벨 | 로거이름 | 메시지"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# __name__: 현재 파일의 모듈 이름("src.main")으로 로거를 만들어, 로그가 어디서 나왔는지 표시
logger = logging.getLogger(__name__)

# get_settings()를 호출하여 환경변수 객체 가져오기 (CORS 허용 주소 설정에 사용)
settings = get_settings()


# APP Lifespan
# L-1. lifespan 정의
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ON. [StartUp] 앱이 켜질 때 실행
    logger.info("🔋 서버가 시작됩니다.")
    # ON-D. DB 연결
    try:
        # ON-D-C. DB 연결 체크
        await check_db_connection()
        # ON-D-S. DB 연결 성공
        logger.info("🟢 DB 연결에 성공했습니다.")
    except Exception as db_err:
        # ON-D-F. DB 연결 실패
        logger.critical(f"🔴 DB 연결에 실패했습니다. {db_err}")
        raise  # DB 연결 실패 시 바로 종료되도록. 만약 서버는 그대로 두고싶다면 주석 처리
    # ON-V. Vector DB 연결
    try:
        # ON-V-I. Vector DB 클라이언트 생성 (src/core/vector_db.py 참고)
        init_vector_db()
        # ON-V-C. Vector DB 연결 체크
        await check_vector_db_connection()
        # ON-V-P. 문서 벡터를 저장할 컬렉션 준비
        await ensure_collection()
        # ON-V-S. Vector DB 연결 성공
        logger.info("🟢 Vector DB 연결에 성공했습니다.")
    except Exception as vdb_err:
        # ON-V-F. Vector DB 연결 실패
        logger.critical(f"🔴 Vector DB 연결에 실패했습니다. {vdb_err}")
        raise  # Vector DB 연결 실패 시 바로 종료되도록. 만약 서버는 그대로 두고싶다면 주석 처리
    # ON-M. 임베딩 서버(Embedding Model) 연결
    #  - HTTP 클라이언트 생성 -> 짧은 문장을 실제로 임베딩해서 연결/모델/차원 확인
    #  - 개발 중에는 _deploy 폴더에서 docker compose up -d embedding 으로 먼저 켜 두어야 함
    try:
        # ON-M-I. 임베딩 HTTP 클라이언트 생성 (src/core/embedding.py 참고)
        init_embedding()
        # ON-M-C. 임베딩 서버 연결 체크
        await check_embedding_connection()
        # ON-M-S. 임베딩 서버 연결 성공
        logger.info("🟢 임베딩 서버 연결에 성공했습니다.")
    except Exception as emb_err:
        # ON-M-F. 임베딩 서버 연결 실패
        logger.critical(f"🔴 임베딩 서버 연결에 실패했습니다. {emb_err}")
        raise  # 임베딩 서버 연결 실패 시 바로 종료되도록. 만약 서버는 그대로 두고싶다면 주석 처리
    # ON-E. App 실행
    yield

    # OFF. [ShutDown] 앱이 꺼질 때 실행
    logger.info("🪫 서버가 종료됩니다.")
    # OFF-D. DB 연결 정리
    try:
        # OFF-D-C. DB 클로즈
        await close_db()
        # OFF-D-S. DB 연결 정리 성공
        logger.info("❎ DB 연결이 종료되었습니다.")
    except Exception as db_err:
        # OFF-D-F. DB 연결 정리 실패
        logger.error(f"⛔️ DB 연결 정리에 실패했습니다. {db_err}")
    # OFF-V. Vector DB 연결 정리
    try:
        # OFF-V-C. Vector DB 클로즈
        await close_vector_db()
        # OFF-V-S. Vector DB 연결 정리 성공
        logger.info("❎ Vector DB 연결이 종료되었습니다.")
    except Exception as vdb_err:
        # OFF-V-F. Vector DB 연결 정리 실패
        logger.error(f"⛔️ Vector DB 연결 정리에 실패했습니다. {vdb_err}")
    # OFF-M. 임베딩 서버 연결 정리
    try:
        # OFF-M-C. 임베딩 HTTP 클라이언트 클로즈
        await close_embedding()
        # OFF-M-S. 임베딩 서버 연결 정리 성공
        logger.info("❎ 임베딩 서버 연결이 종료되었습니다.")
    except Exception as emb_err:
        # OFF-M-F. 임베딩 서버 연결 정리 실패
        logger.error(f"⛔️ 임베딩 서버 연결 정리에 실패했습니다. {emb_err}")


# L-2. FastAPI 인스턴스 생성 시 lifespan(L-1)을 따름
app = FastAPI(lifespan=lifespan)


# CORS 설정 🖥️
# CORS: 브라우저가 "다른 주소(도메인)의 서버"로 요청을 보낼 때, 서버가 허용했는지 확인하는 보안 규칙
app.add_middleware(
    CORSMiddleware,
    # allow_origins=["*"] -> settings.cors_origins
    #  - 기존: "*"(모든 사이트 허용) + allow_credentials=True(쿠키/인증정보 허용) 조합
    #    => 어떤 악성 사이트든 로그인한 사용자의 쿠키를 실어서 우리 API를 호출할 수 있는 위험
    #  - 변경: .env의 CORS_ORIGINS에 적힌 주소(우리 프론트엔드)에서 온 요청만 허용
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health Check API ✅
@app.get("/health-check", tags=["Health Check"])
async def health_check():
    return {
        "status": "healthy",
    }


# APP Router 등록 🚥
app.include_router(api_router)
