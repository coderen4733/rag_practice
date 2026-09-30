from fastapi import APIRouter

from src.services.iam.auth.router import auth_router
from src.services.iam.user.router import user_router

# [수정] 문서(Document) 라우터 import 추가
from src.services.rag.document.router import document_router

api_router = APIRouter()

# 각 라우터를 여기서 api_router에 등록한다
# api_router.include_router(라우터명)

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["인증인가(Auth)"],
)

api_router.include_router(
    user_router,
    prefix="/users",
    tags=["사용자(User)"],
)

# [수정] 문서(Document) 라우터 등록
#  - 기존: auth, user 라우터만 등록
#  - 변경: /documents 주소로 문서 등록/조회/삭제 API 추가
api_router.include_router(
    document_router,
    prefix="/documents",
    tags=["문서(Document)"],
)
