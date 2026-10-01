from fastapi import APIRouter

from src.services.iam.auth.router import auth_router
from src.services.iam.user.router import user_router
from src.services.rag.chat.router import chat_router
from src.services.rag.document.router import document_router
from src.services.rag.search.router import search_router

api_router = APIRouter()

# 각 라우터를 여기서 api_router에 등록한다
# api_router.include_router(라우터명)

# 인증/인가(Auth) 라우터
api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["인증인가(Auth)"],
)

# 사용자/계정(User) 라우터
api_router.include_router(
    user_router,
    prefix="/users",
    tags=["사용자(User)"],
)

# 문서(Document) 라우터
api_router.include_router(
    document_router,
    prefix="/documents",
    tags=["문서(Document)"],
)

# 문서 검색(Search) 라우터
api_router.include_router(
    search_router,
    prefix="/search",
    tags=["문서 검색(Search)"],
)

# 챗봇(Chat) 라우터 등록
api_router.include_router(
    chat_router,
    prefix="/chat",
    tags=["챗봇(Chat)"],
)
