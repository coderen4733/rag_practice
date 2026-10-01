from fastapi import APIRouter, status

from src.common.response import ResponseSchema
from src.services.iam.auth.dependencies import CurrentUser
from src.services.rag.search import service as search_service
from src.services.rag.search.schemas import SearchReq, SearchRes

search_router = APIRouter()


# 문서 검색 API - 로그인한 사용자 누구나
@search_router.post(
    "/",
    response_model=ResponseSchema[SearchRes],
    status_code=status.HTTP_200_OK,
)
async def search_documents(
    dto: SearchReq,
    # 로그인한 사용자만 통과 (토큰 없음/잘못됨 => 401)
    #  - 검색은 DB를 사용하지 않지만, 로그인 확인(get_current_user)에서 DB 세션을 사용함
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await search_service.search_documents(dto)
    # 2. Router -> FrontEnd
    return {
        "message": "문서 검색에 성공했습니다.",
        "data": data,
    }
