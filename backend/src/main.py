from contextlib import asynccontextmanager  # Lifespan 생성

from fastapi import Depends, FastAPI  # FastAPI로 Back-End 구성
from fastapi.middleware.cors import (
    CORSMiddleware,  # CORS 설정을 위한 Middleware
)

from src.api import api_router


# APP Lifespan
# L-1. lifespan 정의
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ON. [StartUp] 앱이 켜질 때 실행
    print("서버가 시작됩니다.")
    # ON-D. PostgresDB 연결
    # ON-V. QdrantVDB 연결
    # ON-R. RedisCloud 연결
    # ON-E. App 실행
    yield

    # OFF. [ShutDown] 앱이 꺼질 때 실행
    print("서버가 종료됩니다.")
    # OFF-D. PostgresDB 커넥션 정리
    # OFF-V. QdrantVDB 커넥션 정리
    # OFF-R. RedisCloud 커넥션 정리


# L-2. FastAPI 인스턴스 생성 시 lifespn(L-1)을 따름
app = FastAPI(lifespan=lifespan)


# CORS 설정 🖥️
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 테스트용이므로 모두 허용
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
