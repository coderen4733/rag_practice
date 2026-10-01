#  * 문서(Document) API 주소(라우터)
#  - 문서 등록 / 목록 조회 / 상세 조회 / 삭제 API
#    - 등록, 삭제: 관리자(admin, manager)만 가능
#    - 목록, 상세 조회: 로그인한 사용자 누구나 가능

from typing import Annotated

# File, UploadFile: 파일 업로드를 받기 위한 FastAPI 도구 (python-multipart 패키지 필요)
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.response import ResponseSchema
from src.core.database import get_db_session
from src.services.iam.auth.dependencies import AdminOrManagerUser, CurrentUser
from src.services.rag.document import service as document_service
from src.services.rag.document.schemas import (
    DocumentDeleteRes,
    DocumentReadListQuery,
    DocumentReadListRes,
    DocumentRes,
)

document_router = APIRouter()


# 문서(Document) 등록(C) API - 관리자(admin, manager) 전용
#  - 요청 형식: multipart/form-data (JSON이 아니라 "파일 첨부" 형식)
#  - Swagger(/docs)에서는 "Choose File" 버튼으로 파일을 골라서 테스트 가능
@document_router.post(
    "/",
    response_model=ResponseSchema[DocumentRes],
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    # UploadFile: 업로드된 파일 (파일 이름, 내용을 읽는 기능 등을 가짐)
    file: Annotated[UploadFile, File(description="등록할 문서 파일 (.txt, .md)")],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    # admin 또는 manager만 통과 (토큰 없음 => 401 / 권한 부족 => 403)
    current_user: AdminOrManagerUser,
) -> dict:
    # 1. Router <- Service
    data = await document_service.upload_document(session, file, current_user)
    # 2. Router -> FrontEnd
    return {
        "message": "문서 등록에 성공했습니다.",
        "data": data,
    }


# 문서(Document) 목록 조회(R-L) API - 로그인한 사용자 누구나
@document_router.get(
    "/",
    response_model=ResponseSchema[DocumentReadListRes],
    status_code=status.HTTP_200_OK,
)
async def read_documents_list(
    # 필터/정렬/페이지 쿼리 파라미터 (사용자 목록 조회와 같은 방식)
    query: Annotated[DocumentReadListQuery, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await document_service.read_documents_list(session, query)
    # 2. Router -> FrontEnd
    return {
        "message": "문서 목록 조회에 성공했습니다.",
        "data": data,
    }


# 문서(Document) 상세 조회(R-D) API - 로그인한 사용자 누구나
#  - 처리 상태(status), 청크 개수, 실패 이유 등을 확인할 때 사용
@document_router.get(
    "/{document_id}",
    response_model=ResponseSchema[DocumentRes],
    status_code=status.HTTP_200_OK,
)
async def read_document(
    document_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: CurrentUser,
) -> dict:
    # 1. Router <- Service
    data = await document_service.read_document(session, document_id)
    # 2. Router -> FrontEnd
    return {
        "message": "문서 조회에 성공했습니다.",
        "data": data,
    }


# 문서(Document) 삭제(D) API - 관리자(admin, manager) 전용
#  - DB의 문서 정보와 Qdrant의 청크를 함께 삭제
@document_router.delete(
    "/{document_id}",
    response_model=ResponseSchema[DocumentDeleteRes],
    status_code=status.HTTP_200_OK,
)
async def delete_document(
    document_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: AdminOrManagerUser,
) -> dict:
    # 1. Router <- Service
    data = await document_service.delete_document(session, document_id)
    # 2. Router -> FrontEnd
    return {
        "message": "문서 삭제에 성공했습니다.",
        "data": data,
    }
